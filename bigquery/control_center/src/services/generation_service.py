import time
import yaml
import json

from services.bq_client import get_bq_client
from google.cloud import bigquery
from google.cloud import aiplatform
from google.cloud import storage
import os
import logging

# Suppress chatty Vertex AI SDK logs
logging.getLogger("google.cloud.aiplatform").setLevel(logging.WARNING)

def update_ongoing_state(job_ids=None, prefixes=None, total_rows=None, clear=False, state_path="state.json"):
    """Updates state.json with ongoing generation details."""
    try:
        if not os.path.exists(state_path):
            return
            
        with open(state_path, 'r') as f:
            state = json.load(f)
            
        if clear:
            state.pop('ongoing_generation', None)
        else:
            ongoing = state.get('ongoing_generation', {})
            if job_ids:
                if 'job_ids' not in ongoing: ongoing['job_ids'] = {}
                ongoing['job_ids'].update(job_ids)
            if prefixes:
                if 'prefixes' not in ongoing: ongoing['prefixes'] = {}
                ongoing['prefixes'].update(prefixes)
            if total_rows is not None:
                ongoing['total_rows'] = total_rows
            state['ongoing_generation'] = ongoing
            
        temp_state_path = state_path + ".tmp"
        with open(temp_state_path, 'w') as f:
            json.dump(state, f, indent=4)
        os.rename(temp_state_path, state_path)
    except Exception:
        pass # Ignore errors to avoid breaking the main flow

def wait_for_jobs_and_get_prefixes(jobs, bucket, log_cb, progress_cb, is_cancelled, total_rows, state_path="state.json"):
    """Polls jobs until completion and returns target prefixes."""
    all_done = False
    previous_states = {t: None for t in jobs.keys()}
    while not all_done:
        if is_cancelled():
            log_cb("Job cancelled by user. Attempting to cancel Vertex AI jobs...\n")
            for t, j in jobs.items():
                try:
                    j.cancel()
                except Exception: pass
                if progress_cb:
                    progress_cb(target=t, state="CANCELLED", total=0)
            update_ongoing_state(clear=True)
            return {'cancelled': True}
            
        all_done = True
        for t, j in jobs.items():
            try:
                res_name = j.resource_name
                if not res_name:
                    log_cb(f"Job {t} resource name not available yet...\n")
                    all_done = False
                    continue
                    
                j = aiplatform.BatchPredictionJob(res_name)
                jobs[t] = j
                
                current_state = j.state.name
                if current_state != previous_states[t]:
                    current_time = time.strftime("%H:%M:%S")
                    log_cb(f"[{current_time}] Job {t} state: {current_state}\n")
                    previous_states[t] = current_state
                
                job_dict = j.to_dict()
                stats = job_dict.get('completionStats', {})
                success_count = int(stats.get('successfulCount', 0))
                failed_count = int(stats.get('failedCount', 0))
                
                # Save prefix to state.json if available
                output_dir = job_dict.get('outputInfo', {}).get('gcsOutputDirectory')
                if output_dir:
                    parts = output_dir.split(f"gs://{bucket}/")
                    if len(parts) > 1:
                        prefix = parts[1] + "/"
                        update_ongoing_state(prefixes={t: prefix}, state_path=state_path)
                
                if progress_cb:
                    progress_cb(target=t, state=j.state.name, success_count=success_count, failed_count=failed_count, total=total_rows)
                from google.cloud.aiplatform.gapic import JobState
                if j.state not in [JobState.JOB_STATE_SUCCEEDED, JobState.JOB_STATE_FAILED, JobState.JOB_STATE_CANCELLED]:
                    all_done = False
            except Exception as e:
                if "has not been created" in str(e) or "NoneType" in str(e):
                    log_cb(f"Job {t} resource not created yet on server...\n")
                else:
                    raise e
                    
        if not all_done:
            for _ in range(30):
                if is_cancelled():
                    break
                time.sleep(1)
                
    # Construct target prefixes for merging
    target_prefixes = {}
    for t, j in jobs.items():
        prefix = f"output/output_{t.lower()}/"
        try:
            job_dict = j.to_dict()
            output_dir = job_dict.get('outputInfo', {}).get('gcsOutputDirectory')
            if output_dir:
                parts = output_dir.split(f"gs://{bucket}/")
                if len(parts) > 1:
                    prefix = parts[1] + "/"
        except Exception as e:
            log_cb(f"Warning: Failed to get specific output directory for {t}: {e}. Using default prefix.\n")
        target_prefixes[t] = prefix
        
    return target_prefixes

def load_and_merge_results(project, dataset, bucket, output_table, target_prefixes, log_cb, storage_client, client, progress_cb=None, state_path="state.json"):
    if progress_cb:
        progress_cb(step_text="[Step 4/4] Retrieving and merging results...")
    output_id = f"{project}.{dataset}.{output_table}"
    for t, prefix in target_prefixes.items():
        log_cb(f"Processing results for {t} from GCS prefix: {prefix}\n")
        
        out_bucket = storage_client.get_bucket(bucket)
        blobs = list(out_bucket.list_blobs(prefix=prefix))
        log_cb(f"Found {len(blobs)} blobs with prefix {prefix}\n")
        
        import os
        os.makedirs('tmp', exist_ok=True)
        local_output_path = f"tmp/batch_output_{t.lower()}.jsonl"
        
        with open(local_output_path, "w") as out_f:
            for b in blobs:
                if b.name.endswith(".jsonl"):
                    content = b.download_as_text()
                    out_f.write(content)
                    out_f.write("\n")
                    
        log_cb(f"Results downloaded to {local_output_path}. Loading to BigQuery...\n")
        
        # Parse results in Python to be more robust
        rows_to_load = []
        import re
        with open(local_output_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    row_id = data.get('id') or data.get('instance', {}).get('id')
                    prediction = data.get('response') or data.get('prediction')
                    
                    # Extract text from prediction
                    text = ""
                    candidates = prediction.get('candidates', []) if prediction else []
                    if candidates:
                        text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                    
                    # Extract generated title/description
                    match = re.search(r'generated (?:title|description):\s*(.*)', text, re.IGNORECASE)
                    extracted_val = match.group(1).strip() if match else text.strip()
                    
                    rows_to_load.append({
                        'id': row_id,
                        'prediction': json.dumps(prediction),
                        'extracted_val': extracted_val
                    })
                except Exception as e:
                    log_cb(f"Warning: Failed to parse JSON line: {e}\n")
                    
        if not rows_to_load:
            log_cb(f"No valid results found for {t}.\n")
            continue
            
        # Load extracted data to BQ temp table
        temp_table_id = f"{project}.{dataset}.temp_batch_{t.lower()}"
        
        job_config = bigquery.LoadJobConfig(
            schema=[
                bigquery.SchemaField("id", "STRING"),
                bigquery.SchemaField("prediction", "STRING"),
                bigquery.SchemaField("extracted_val", "STRING"),
            ],
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        
        load_job = client.load_table_from_json(rows_to_load, temp_table_id, job_config=job_config)
        load_job.result() # Wait for completion
        log_cb(f"Loaded {len(rows_to_load)} results into temp table {temp_table_id}.\n")
        
        # Merge results back
        col_to_update = "title" if t == "Titles" else "description"
        raw_col_to_update = "raw_response_title" if t == "Titles" else "raw_response_description"
        
        sql_merge = f"""
        MERGE `{output_id}` AS O
        USING `{temp_table_id}` AS V
        ON O.id = V.id
        WHEN MATCHED THEN UPDATE SET
          O.{col_to_update} = V.extracted_val,
          O.{raw_col_to_update} = V.prediction,
          O.tries = COALESCE(O.tries, 0) + 1,
          O.updated_at = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (id, {col_to_update}, {raw_col_to_update}, tries, updated_at)
        VALUES (V.id, V.extracted_val, V.prediction, 1, CURRENT_TIMESTAMP());
        """
        
        log_cb(f"Merging results for {t} back to {output_id}...\n")
        client.query(sql_merge).result()
        
        # Clean up temp table and local file (Disabled for debugging)
        # client.query(f"DROP TABLE `{temp_table_id}`").result()
        import os
        # if os.path.exists(local_output_path):
        #     os.remove(local_output_path)
            
        # Clean up GCS files (Disabled for debugging)
        # try:
        #     # Delete input
        #     try:
        #         out_bucket.blob(f"input/input_{t.lower()}.jsonl").delete()
        #     except Exception: pass
        #     # Delete output blobs
        #     for b in blobs:
        #         try:
        #             b.delete()
        #         except Exception: pass
        #     log_cb(f"Cleaned up GCS files for {t}.\n")
        # except Exception as e:
        #     log_cb(f"Warning: Failed to clean up GCS files for {t}: {e}\n")
        log_cb(f"Skipping GCS cleanup for debugging.\n")
        
    # Clear ongoing state after successful merge of all targets
    update_ongoing_state(clear=True, state_path=state_path)

def resume_generation_process(project, dataset, bucket, output_table, job_ids, log_cb, progress_cb, is_cancelled, state_path="state.json"):
    """Resumes a generation process by polling existing jobs."""
    client = get_bq_client(project)
    storage_client = storage.Client(project=project)
    
    # Read total_rows from state.json
    total_rows = 0
    try:
        if os.path.exists(state_path):
            with open(state_path, 'r') as f:
                state = json.load(f)
                ongoing = state.get('ongoing_generation', {})
                total_rows = ongoing.get('total_rows', 0)
            log_cb(f"Retrieved total_rows from state: {total_rows}\n")
    except Exception as e:
        log_cb(f"Warning: Failed to read total_rows from state: {e}\n")
        
    # Recreate jobs
    jobs = {}
    for t, job_id in job_ids.items():
        log_cb(f"Reconnecting to job {t}: {job_id}\n")
        # Extract location from job_id
        import re
        match = re.search(r'locations/([^/]+)/', job_id)
        loc = match.group(1) if match else "global"
        
        aiplatform.init(project=project, location=loc)
        jobs[t] = aiplatform.BatchPredictionJob(job_id)
        
    # Wait for jobs and get prefixes
    if progress_cb:
        progress_cb(step_text="[Step 3/4] Resuming jobs monitoring...")
        
    target_prefixes = wait_for_jobs_and_get_prefixes(jobs, bucket, log_cb, progress_cb, is_cancelled, total_rows, state_path=state_path)
    
    if isinstance(target_prefixes, dict) and 'cancelled' in target_prefixes:
        return target_prefixes
        
    # Merge results
    load_and_merge_results(project, dataset, bucket, output_table, target_prefixes, log_cb, storage_client, client, progress_cb=progress_cb)
    
    return {'success': True, 'total_rows': total_rows}

def run_generation_process(project: str, dataset: str, lang: str, output_table: str, gen_titles: bool, gen_desc: bool, debug: bool, bucket: str, use_images: bool, web_done: bool, id_col: str, title_col: str, desc_col: str, image_col: str, region_val: str = "EU", model_val: str = "gemini-2.5-flash", output_bucket: str = "", log_cb=print, progress_cb=None, is_cancelled=lambda: False, state_path: str = "state.json"):
    """Runs the generation process using Vertex AI Batch Prediction."""
    client = get_bq_client(project)
    
    try:
        # 1. Prepare Tables
        if progress_cb:
            progress_cb(step_text="[Step 1/4] Preparing tables...")
        log_cb("Preparing tables...\n")
        
        input_proc_id = f"{project}.{dataset}.InputProcessing"
        source_id = f"{project}.{dataset}.InputFiltered"
        web_id = f"{project}.{dataset}.InputFilteredWeb"
        
        table_ref = client.get_table(source_id)
        schema_names = [f.name for f in table_ref.schema]
        
        actual_id_col = 'id' if 'id' in schema_names else id_col
        actual_title_col = 'title' if 'title' in schema_names else title_col
        actual_desc_col = 'description' if 'description' in schema_names else desc_col
        
        cols = ["F.*"]
        
        if 'id' not in schema_names:
            cols.append(f"F.{actual_id_col} AS id")
            
        if 'title' not in schema_names:
            cols.append(f"F.{actual_title_col} AS title")
            
        if 'description' not in schema_names:
            cols.append(f"F.{actual_desc_col} AS description")
            
        if 'image_url' not in schema_names:
            if image_col and image_col != 'skip' and image_col in schema_names:
                cols.append(f"F.{image_col} AS image_url")
            else:
                cols.append("CAST(NULL AS STRING) AS image_url")
                
        cols_str = ", ".join(cols)
            
        if web_done:
            sql_input = f"""
            CREATE OR REPLACE TABLE `{input_proc_id}` AS
            SELECT {cols_str}, W.content AS webpage_content
            FROM `{source_id}` AS F
            LEFT JOIN `{web_id}` AS W ON F.{actual_id_col} = W.id;
            """
        else:
            log_cb("Web scraping was not completed. Skipping join with webpage content.\n")
            sql_input = f"""
            CREATE OR REPLACE TABLE `{input_proc_id}` AS
            SELECT {cols_str}, CAST(NULL AS STRING) AS webpage_content
            FROM `{source_id}` AS F;
            """
            
        log_cb(f"Creating table {input_proc_id}...\n")
        client.query(sql_input).result()
        
        output_id = f"{project}.{dataset}.{output_table}"
        
        # Initialize output table if not exists
        sql_output = f"""
        CREATE TABLE IF NOT EXISTS `{output_id}` (
          id STRING,
          title STRING,
          description STRING,
          tries INT64,
          updated_at TIMESTAMP,
          raw_response_title STRING,
          raw_response_description STRING
        );
        """
        log_cb(f"Ensuring output table {output_id} exists...\n")
        client.query(sql_output).result()
        
        # Clean up output table to avoid duplicates from previous failed runs
        log_cb(f"Cleaning up output table {output_id} before generation...\n")
        client.query(f"TRUNCATE TABLE `{output_id}`").result()
        
        # 2. Construct Prompts and Run Batch Prediction
        targets = []
        if gen_titles: targets.append("Titles")
        if gen_desc: targets.append("Descriptions")
        
        if not targets:
            log_cb("No targets selected for generation.\n")
            return {'success': True, 'message': 'No targets selected'}
            
        # Read prompt templates
        prompt_titles_path = "prompts/titles.txt"
        prompt_desc_path = "prompts/descriptions.txt"
        try:
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                prompts_config = config.get('prompts', {})
                prompt_titles_path = prompts_config.get('titles', prompt_titles_path)
                prompt_desc_path = prompts_config.get('descriptions', prompt_desc_path)
        except Exception:
            pass
            
        with open(prompt_titles_path, "r") as f:
            titles_template = f.read()
        with open(prompt_desc_path, "r") as f:
            desc_template = f.read()
            
        # Fetch data for prompt construction
        query_data = f"SELECT * FROM `{input_proc_id}`"
        rows = list(client.query(query_data).result())
        
        # Save total rows to state.json for resume progress
        update_ongoing_state(total_rows=len(rows), state_path=state_path)
        
        # Fetch examples
        query_examples = f"SELECT * FROM `{project}.{dataset}.Examples`"
        examples = []
        try:
            examples = list(client.query(query_examples).result())
        except Exception:
            log_cb("No examples table found. Proceeding without examples.\n")
            
        # Initialize storage client
        storage_client = storage.Client(project=project)
        gcs_bucket = storage_client.get_bucket(bucket)
        
        # Vertex AI will be initialized per attempt in the loop
        
        # Determine publisher
        publisher = "google"
        if model_val.startswith("claude-"):
            publisher = "anthropic"
            
        if progress_cb:
            progress_cb(step_text="[Step 2/4] Creating batch prediction jobs...")
            
        jobs = {}
        
        for target in targets:
            log_cb(f"\n--- Preparing Batch Prediction for {target} ---\n")
            
            instances = []
            for row in rows:
                sys_inst = titles_template if target == "Titles" else desc_template
                sys_inst = sys_inst.replace("{{LANGUAGE}}", lang)
                
                examples_str = ""
                if examples:
                    examples_str = "## Examples\n\n"
                    for ex in examples:
                        examples_str += f"**User:**\n{ex.properties}\n\n**Model:**\n{ex.title if target == 'Titles' else ex.description}\n\n"
                        
                row_dict = dict(row)
                row_dict.pop('id', None)
                row_dict.pop('image_url', None)
                row_dict.pop('webpage_content', None)
                
                properties_str = json.dumps(row_dict)
                input_str = f"## Input\n\n{properties_str}\n"
                
                if use_images and row.image_url:
                    img_filename = row.image_url.split('/')[-1]
                    input_str += f"image_url: gs://{bucket}/images/{img_filename}\n"
                    
                if web_done and row.webpage_content:
                    input_str += f"webpage_content: {row.webpage_content}\n"
                    
                full_prompt = f"## System Instructions\n\n{sys_inst}\n\n{examples_str}{input_str}"
                
                if publisher == "anthropic":
                    json_row = {
                        "custom_id": str(row.id),
                        "request": {
                            "messages": [{"role": "user", "content": full_prompt}],
                            "anthropic_version": "vertex-2023-10-16",
                            "max_tokens": 1000
                        }
                    }
                else:
                    instance = {
                        "contents": [{"role": "user", "parts": [{"text": full_prompt}]}]
                    }
                    json_row = {
                        "id": str(row.id),
                        "request": instance
                    }
                instances.append(json.dumps(json_row))
                
            blob_path = f"input/input_{target.lower()}.jsonl"
            blob = gcs_bucket.blob(blob_path)
            blob.upload_from_string("\n".join(instances), content_type="application/jsonl")
            log_cb(f"Uploaded input for {target} to gs://{bucket}/{blob_path}\n")
            
            # Determine locations based on region with fallback
            locs = []
            
            # Load config.yaml to get supported locations
            supported_locs = []
            try:
                import yaml
                with open('config.yaml', 'r') as f:
                    config = yaml.safe_load(f)
                    models_config = config.get('models', [])
                    for m in models_config:
                        if m.get('value') == model_val:
                            supported_locs = m.get('supported_locations', [])
                            break
            except Exception:
                pass
                
            if supported_locs:
                # Use supported locations from config
                if region_val.lower() in supported_locs:
                    locs.append(region_val.lower())
                    
                # Add encompassing multi-region if in list
                if region_val.lower().startswith("us-") and "us" in supported_locs and "us" not in locs:
                    locs.append("us")
                elif region_val.lower().startswith("europe-") and "eu" in supported_locs and "eu" not in locs:
                    locs.append("eu")
                    
                # Add remaining supported locations
                for l in supported_locs:
                    if l not in locs:
                        locs.append(l)
            else:
                # Fallback to hardcoded rules if no config found
                locs.append(region_val.lower())
                if region_val.lower().startswith("us-") and "us" not in locs:
                    locs.append("us")
                elif region_val.lower().startswith("europe-") and "eu" not in locs:
                    locs.append("eu")
                if publisher == "google" and "global" not in locs:
                    locs.append("global")
                
            attempts = []
            for l in locs:
                attempts.append({"loc": l, "use_full_path": True})
                attempts.append({"loc": l, "use_full_path": False})
                
            success = False
            start_time = time.strftime("%H:%M:%S")
            for attempt in attempts:
                loc = attempt["loc"]
                use_full_path = attempt["use_full_path"]
                
                if use_full_path:
                    publisher = "google"
                    if model_val.startswith("claude-"):
                        publisher = "anthropic"
                    elif model_val.startswith("mistral-"):
                        publisher = "mistralai"
                    model_name = f"projects/{project}/locations/{loc}/publishers/{publisher}/models/{model_val}"
                else:
                    model_name = model_val
                    
                log_cb(f"Attempting with location={loc} and model={model_name}...\n")
                try:
                    aiplatform.init(project=project, location=loc)
                    job = aiplatform.BatchPredictionJob.create(
                        job_display_name=f"feedgen_{target.lower()}_{int(time.time())}",
                        model_name=model_name,
                        gcs_source=f"gs://{bucket}/{blob_path}",
                        gcs_destination_prefix=f"gs://{bucket}/output/output_{target.lower()}",
                        instances_format="jsonl",
                        predictions_format="jsonl",
                        sync=False,
                    )
                    log_cb(f"Job creation initiated for {target}...\n")
                    
                    # Sleep to avoid race condition in SDK
                    time.sleep(5)
                    
                    jobs[target] = job
                    log_cb(f"Job created for {target}: {job.resource_name}\n")
                    update_ongoing_state(job_ids={target: job.resource_name}, state_path=state_path)
                    success = True
                    if progress_cb:
                        progress_cb(target=target, state="PENDING", start_time=start_time)
                    break
                except Exception as e:
                    log_cb(f"Attempt failed with location={loc}: {e}\n")
                    
            if not success:
                raise Exception(f"Failed to create batch prediction job for {target} after all attempts.")
                
        # Wait for all jobs and get prefixes
        if progress_cb:
            progress_cb(step_text="[Step 3/4] Running jobs in Vertex AI...")
            
        target_prefixes = wait_for_jobs_and_get_prefixes(jobs, bucket, log_cb, progress_cb, is_cancelled, len(rows), state_path=state_path)
        
        if isinstance(target_prefixes, dict) and 'cancelled' in target_prefixes:
            return target_prefixes
            
        # Call the separated merge function
        load_and_merge_results(project, dataset, bucket, output_table, target_prefixes, log_cb, storage_client, client, progress_cb=progress_cb)
            
        return {'success': True, 'total_rows': len(rows)}
        
    except Exception as e:
        log_cb(f"Error: {e}\n")
        raise e
