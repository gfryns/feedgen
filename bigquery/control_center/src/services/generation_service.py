import asyncio
import time
import yaml
from services.bq_client import get_bq_client
from google.cloud import bigquery

def run_generation_process(project: str, dataset: str, lang: str, workers: int, output_table: str, gen_titles: bool, gen_desc: bool, debug: bool, bucket: str, use_images: bool, web_done: bool, id_col: str, title_col: str, desc_col: str, image_col: str, log_cb=print, progress_cb=None, is_cancelled=lambda: False):
    """Runs the generation process by calling stored procedures in BigQuery."""
    client = get_bq_client(project)
    
    try:
        # 1. Prepare Tables
        log_cb("Preparing tables...\n")
        
        input_proc_id = f"{project}.{dataset}.InputProcessing"
        source_id = f"{project}.{dataset}.InputFiltered"
        web_id = f"{project}.{dataset}.InputFilteredWeb"
        
        table_ref = client.get_table(source_id)
        schema_names = [f.name for f in table_ref.schema]
        
        actual_id_col = 'id' if 'id' in schema_names else id_col
        actual_title_col = 'title' if 'title' in schema_names else title_col
        actual_desc_col = 'description' if 'description' in schema_names else desc_col
        
        # Determine image_url string. If not in schema and image_col was skipped, we use CAST(NULL AS STRING)
        if 'image_url' in schema_names:
            img_sel = "F.image_url"
        elif image_col and image_col != 'skip' and image_col in schema_names:
            img_sel = f"F.{image_col} AS image_url"
        else:
            img_sel = "CAST(NULL AS STRING) AS image_url"
            
        if web_done:
            sql_input = f"""
            CREATE OR REPLACE TABLE `{input_proc_id}` AS
            SELECT
              F.{actual_id_col} AS id, F.{actual_title_col} AS title, F.{actual_desc_col} AS description, {img_sel},
              W.content AS webpage_content
            FROM `{source_id}` AS F
            LEFT JOIN `{web_id}` AS W ON F.{actual_id_col} = W.id;
            """
        else:
            log_cb("Web scraping was not completed. Skipping join with webpage content.\n")
            sql_input = f"""
            CREATE OR REPLACE TABLE `{input_proc_id}` AS
            SELECT
              F.{actual_id_col} AS id, F.{actual_title_col} AS title, F.{actual_desc_col} AS description, {img_sel},
              CAST(NULL AS STRING) AS webpage_content
            FROM `{source_id}` AS F;
            """
            
        log_cb(f"Creating table {input_proc_id}...\n")
        client.query(sql_input).result()
        
        output_id = f"{project}.{dataset}.{output_table}"
        
        # Re-deploy procedures for specific output table
        log_cb(f"Configuring generation for destination table `{output_id}`...\n")
        
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
            
        with open("generation.sql", "r") as f:
            gen_sql = f.read()
        with open(prompt_titles_path, "r") as f:
            titles_prompt = f.read()
        with open(prompt_desc_path, "r") as f:
            descriptions_prompt = f.read()
            
        gen_sql = gen_sql.replace("[DATASET]", f"{project}.{dataset}")
        gen_sql = gen_sql.replace("[OUTPUT_TABLE]", output_id)
        gen_sql = gen_sql.replace("-- TITLES_PROMPT", titles_prompt)
        gen_sql = gen_sql.replace("-- DESCRIPTIONS_PROMPT", descriptions_prompt)
        
        client.query(gen_sql).result()
        
        sql_output = f"""
        CREATE OR REPLACE TABLE `{output_id}` AS
        SELECT
          {actual_id_col} AS id,
          CAST(NULL AS STRING) AS title,
          CAST(NULL AS STRING) AS description,
          0 AS tries,
          CAST(NULL AS TIMESTAMP) AS updated_at,
          CAST(NULL AS STRING) AS raw_response_title,
          CAST(NULL AS STRING) AS raw_response_description
        FROM `{source_id}`;
        """
        
        log_cb(f"Initializing output table {output_id}...\n")
        client.query(sql_output).result()
        
        # 2. Run Stored Procedures
        targets = []
        if gen_titles: targets.append("Titles")
        if gen_desc: targets.append("Descriptions")
        
        if not targets:
            log_cb("No targets selected for generation.\n")
            return {'success': True, 'message': 'No targets selected'}
            
        batch_size = 15
        
        # Get total rows for progress bar
        total_query = f"SELECT COUNT(*) as total FROM `{input_proc_id}`"
        total_rows = list(client.query(total_query).result())[0].total
        
        total_targets = len(targets)
        debug_val = "TRUE" if debug else "FALSE"
        use_images_val = "TRUE" if use_images else "FALSE"
        
        for step_idx, target in enumerate(targets):
            log_cb(f"\n--- Generating {target} ---\n")
            
            if progress_cb:
                progress_cb(total=total_rows, progress=0, step_text=f"Step {step_idx + 1}/{total_targets}: Generating {target}...")
                
            procedure = f"BatchedUpdate{target}"
            
            jobs = []
            if workers <= 1:
                sql = f"CALL `{project}.{dataset}`.{procedure}({batch_size}, '{lang}', NULL, NULL, NULL, '{bucket}', {use_images_val}, {debug_val});"
                log_cb(f"Running: {sql}\n")
                job = client.query(sql)
                jobs.append(job)
            else:
                log_cb(f"Splitting work into {workers} parallel parts...\n")
                for part in range(workers):
                    sql = f"CALL `{project}.{dataset}`.{procedure}({batch_size}, '{lang}', {workers}, {part}, NULL, '{bucket}', {use_images_val}, {debug_val});"
                    log_cb(f"Starting worker {part}/{workers}: {sql}\n")
                    job = client.query(sql)
                    jobs.append(job)
                    
                    # Stagger worker start times
                    if part < workers - 1:
                        for _ in range(5):
                            if is_cancelled():
                                return {'cancelled': True}
                            time.sleep(1)
                    
            # Polling for progress
            if target == 'Titles':
                processed_query = f"SELECT COUNT(*) as processed FROM `{output_id}` WHERE title IS NOT NULL"
            else:
                processed_query = f"SELECT COUNT(*) as processed FROM `{output_id}` WHERE description IS NOT NULL"
                
            all_done = False
            while not all_done:
                if is_cancelled():
                    log_cb("App is shutting down. Cancelling active BigQuery jobs...\n")
                    for job in jobs:
                        if not job.done():
                            try: job.cancel()
                            except Exception: pass
                    return {'cancelled': True}

                all_done = True
                has_error = False
                for i, job in enumerate(jobs):
                    job.reload()
                    if not job.done():
                        all_done = False
                    elif job.exception():
                        error_msg = str(job.exception()).lower()
                        if "too many concurrent queries" in error_msg or "rate limit" in error_msg or "exceeded rate limits" in error_msg or "could not serialize access" in error_msg or "concurrent update" in error_msg:
                            log_cb(f"Concurrency/Rate limit hit for worker {i}. Retrying after a short delay...\n")
                            for _ in range(15):
                                if is_cancelled(): break
                                time.sleep(1)
                            if is_cancelled(): return {'cancelled': True}
                            jobs[i] = client.query(job.query)
                            all_done = False
                        else:
                            log_cb(f"ERROR in job: {job.exception()}\n")
                            has_error = True
                            all_done = True
                            break
                        
                if has_error:
                    raise Exception("Generation failed due to an error in one of the jobs.")

                try:
                    processed_rows = list(client.query(processed_query).result())[0].processed
                    if progress_cb:
                        progress_cb(progress=processed_rows)
                except Exception:
                    pass
                    
                if not all_done:
                    for _ in range(5):
                        if is_cancelled(): break
                        time.sleep(1)
                    
            log_cb(f"Finished generation for {target}.\n")
            
        return {'success': True, 'total_rows': total_rows}
        
    except Exception as e:
        log_cb(f"Error: {e}\n")
        raise e
