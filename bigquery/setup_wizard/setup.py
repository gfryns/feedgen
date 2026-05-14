import json
import os
import subprocess
import sys
import time
from google.cloud import bigquery

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("Warning: config.json is corrupted. Starting with empty config.")
                return {}
    return {}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def prompt_default(prompt_text, default_value):
    val = input(f"{prompt_text} (default: {default_value}): ").strip()
    return val if val else default_value

def main():
    print("=== FeedGen BigQuery Wizard ===")
    config = load_config()
    # Step 1: Basic Configuration
    print("\n--- Step 1: Basic Configuration ---")
    config['project'] = prompt_default("GCP Project ID", config.get('project', ''))
    config['dataset'] = prompt_default("BigQuery Dataset Name", config.get('dataset', 'feedgen_dataset'))
    config['raw_table'] = prompt_default("Raw Feed Table Name", config.get('raw_table', 'InputRaw'))
    config['region'] = prompt_default("Region", config.get('region', 'EU'))
    config['model'] = prompt_default("Model Name", config.get('model', 'gemini-2.5-flash'))
    config['connection'] = prompt_default("Connection Name", config.get('connection', 'feedgen_connection'))
    
    save_config(config)
    
    try:
        client = bigquery.Client(project=config['project'])
    except Exception as e:
        print(f"Error initializing BigQuery client: {e}")
        print("Make sure you have active credentials and the project ID is correct.")
        sys.exit(1)
        
    # Step 2: Setup
    print("\n--- Step 2: BigQuery Setup ---")
    run_setup = input("Do you need to deploy models & procedures? (Y/n): ").strip().lower()
    if run_setup == 'y' or run_setup == '':
        print("Setting up BigQuery resources and stored procedures...")
        try:
            # 1. Set project
            print(f"Setting GCP project to '{config['project']}'...")
            subprocess.run(["gcloud", "config", "set", "project", config['project']], check=True)
            
            # 2. Create dataset
            print(f"Creating BigQuery dataset '{config['dataset']}'...")
            subprocess.run(["bq", "--location=" + config['region'], "mk", "--dataset", f"{config['project']}:{config['dataset']}"], check=False)
            
            # 3. Create connection
            print(f"Creating BigQuery connection '{config['connection']}'...")
            subprocess.run(["bq", "mk", "--connection", "--location=" + config['region'], "--project_id=" + config['project'], "--connection_type=CLOUD_RESOURCE", config['connection']], check=False)
            
            # 4. Enable API
            print("Enabling Vertex AI API...")
            subprocess.run(["gcloud", "services", "enable", "aiplatform.googleapis.com", "--project=" + config['project']], check=True)
            
            # 5. Get service account
            print("Fetching service account for connection...")
            res = subprocess.run(["bq", "--project_id=" + config['project'], "show", "--connection", "--format=json", f"{config['region']}.{config['connection']}"], capture_output=True, text=True, check=True)
            sa = json.loads(res.stdout)['cloudResource']['serviceAccountId']
            print(f"Found service account: {sa}")
            
            # 6. Grant IAM role
            print("Granting Vertex AI User role to service account...")
            subprocess.run(["gcloud", "projects", "add-iam-policy-binding", config['project'],
                            "--member=serviceAccount:" + sa,
                            "--role=roles/aiplatform.user"], check=True)
            
            print("Waiting for IAM permissions to propagate (20s)...")
            time.sleep(20)
            
            # 7. Create model
            print("Creating Gemini remote model in BigQuery...")
            sql_model = f"""
            CREATE OR REPLACE MODEL `{config['project']}.{config['dataset']}.GeminiModel`
              REMOTE WITH CONNECTION `{config['project']}.{config['region']}.{config['connection']}`
              OPTIONS (endpoint = '{config['model']}');
            """
            client.query(sql_model).result()
            print("Model created.")
            
            # 8. Install functions and procedures
            print("Installing stored functions and procedures...")
            
            with open("generation.sql", "r") as f:
                gen_sql = f.read()
                
            with open("prompts/titles.txt", "r") as f:
                titles_prompt = f.read()
            with open("prompts/descriptions.txt", "r") as f:
                descriptions_prompt = f.read()
                
            gen_sql = gen_sql.replace("[DATASET]", config['dataset'])
            gen_sql = gen_sql.replace("-- TITLES_PROMPT", titles_prompt)
            gen_sql = gen_sql.replace("-- DESCRIPTIONS_PROMPT", descriptions_prompt)

            
            client.query(gen_sql).result()
            print("Functions and procedures installed.")
            
        except Exception as e:
            print(f"Error during setup: {e}")
            
    # Step 2: Input Filtering
    print("\n--- Step 3: Input Filtering ---")
    columns = []
    print("Fetching table schema...")
    try:
        raw_table_ref = config['raw_table']
        if '.' in raw_table_ref:
            parts = raw_table_ref.split('.')
            if len(parts) == 3:
                table = client.get_table(f"{parts[0]}.{parts[1]}.{parts[2]}")
            elif len(parts) == 2:
                table = client.get_table(f"{config['project']}.{parts[0]}.{parts[1]}")
            else:
                table = client.get_table(f"{config['project']}.{config['dataset']}.{raw_table_ref}")
        else:
            table = client.get_table(f"{config['project']}.{config['dataset']}.{raw_table_ref}")
            
        columns = [field.name for field in table.schema]
    except Exception as e:
        print(f"Warning: Could not fetch table schema: {e}")
        
    import re
    
    id_candidates = [c for c in columns if re.search(r'(id|sku)', c, re.I)]
    title_candidates = [c for c in columns if re.search(r'(title|name)', c, re.I)]
    desc_candidates = [c for c in columns if re.search(r'(desc|text|summary)', c, re.I)]
    
    if columns:
        print(f"Available columns: {', '.join(columns)}")
        
    def select_column(col_name, candidates, config_key, default_val):
        current_val = config.get(config_key, default_val)
        options = []
        mapping = {}
        
        idx = 1
        if current_val and current_val in columns:
            options.append(f"Use previously entered value: '{current_val}'")
            mapping[str(idx)] = 'prev'
            idx += 1
            
        if candidates:
            options.append(f"Pick from suggestions: {', '.join(candidates)}")
            mapping[str(idx)] = 'suggest'
            idx += 1
            
        options.append("Enter a column name manually")
        mapping[str(idx)] = 'manual'
        
        print(f"\nSelect column for {col_name}:")
        for i, opt in enumerate(options, 1):
            print(f"{i}. {opt}")
            
        choice = input(f"Enter choice (1-{len(options)}): ").strip()
        
        action = mapping.get(choice, 'manual' if choice == str(idx) else 'default')
        
        if action == 'prev':
            return current_val
        elif action == 'suggest':
            if len(candidates) == 1:
                return candidates[0]
            else:
                print("Available suggestions:")
                for i, c in enumerate(candidates, 1):
                    print(f"  {i}. {c}")
                c_choice = input(f"Select suggestion (1-{len(candidates)}): ").strip()
                try:
                    c_idx = int(c_choice) - 1
                    if 0 <= c_idx < len(candidates):
                        return candidates[c_idx]
                except ValueError:
                    pass
                print("Invalid choice, using first suggestion.")
                return candidates[0]
        elif action == 'manual':
            return input(f"Enter column name for {col_name}: ").strip()
        else:
            print("Invalid choice, using default or first candidate.")
            if current_val and current_val in columns:
                return current_val
            return candidates[0] if candidates else default_val

    config['id_col'] = select_column("Unique ID", id_candidates, 'id_col', 'id')
    config['title_col'] = select_column("Current Title", title_candidates, 'title_col', 'title')
    config['desc_col'] = select_column("Current Description", desc_candidates, 'desc_col', 'description')
    config['include_cols'] = prompt_default("Columns to include (comma-separated, or * for all)", config.get('include_cols', 'brand,category'))
    config['filters'] = prompt_default("Additional SQL clauses (e.g., WHERE clicks > 10 ORDER BY clicks DESC LIMIT 10)", config.get('filters', ''))
    
    save_config(config)
    
    # Construct SQL for InputFiltered
    if config['include_cols'].strip() == '*':
        cols_str = '*'
    else:
        cols = [config['id_col'], config['title_col'], config['desc_col']]
        cols.extend([c.strip() for c in config['include_cols'].split(',') if c.strip()])
        cols_str = ", ".join(list(set(cols))) # Remove duplicates just in case
        
    raw_table_ref = config['raw_table']
    if '.' in raw_table_ref:
        parts = raw_table_ref.split('.')
        raw_table_ref = ".".join([f"`{p}`" for p in parts])
    else:
        raw_table_ref = f"`{config['project']}.{config['dataset']}.{config['raw_table']}`"
        
    sql_filter = f"""
    CREATE OR REPLACE TABLE `{config['project']}.{config['dataset']}.InputFiltered` AS
    SELECT {cols_str}
    FROM {raw_table_ref}
    {config['filters']}
    """
    
    print(f"Creating InputFiltered table...")
    try:
        client.query(sql_filter).result()
        print("InputFiltered table created successfully.")
    except Exception as e:
        print(f"Error creating InputFiltered table: {e}")
        
    # Step 4: Enrich Data (Product Pages)
    print("\n--- Step 4: Enrich Data (Web Pages) ---")
    run_web = input("Do you want to run the product page scraping workflow? (y/N): ").strip().lower()
    if run_web == 'y':
        url_col = prompt_default("URL column name", config.get('url_col', 'link'))
        selector = prompt_default("CSS Selector for description", config.get('selector', 'div[data-testid^="item-description"]'))
        print("Running 1_parse_descriptions.py...")
        try:
            subprocess.run([sys.executable, "workflows/1_parse_descriptions.py",
                            "--dataset", config['dataset'],
                            "--url_column", url_col,
                            "--selector", selector], check=True)
        except Exception as e:
            print(f"Error running web scraping: {e}")

    # Step 5: Enrich Data (Images)
    print("\n--- Step 5: Enrich Data (Images) ---")
    run_images = input("Do you want to run the image description workflow? (y/N): ").strip().lower()
    if run_images == 'y':
        bucket_name = prompt_default("GCS Bucket name", f"{config['project']}-images")
        print("Running 2_process_images.py...")
        try:
            subprocess.run([sys.executable, "workflows/2_process_images.py", 
                            "--dataset", config['dataset'],
                            "--bucket", bucket_name,
                            "--connection", config['connection']], check=True)
        except Exception as e:
            print(f"Error running image processing: {e}")
            
    # Step 6: Manage Examples
    print("\n--- Step 6: Manage Examples ---")
    print("This step is to teach the model what 'good' looks like.")
    print("You should provide a few best-in-class examples of titles and descriptions (2-5 examples).")
    run_examples = input("Do you want to run the examples management? (Y/n): ").strip().lower()
    if run_examples == 'y' or run_examples == '':
        print("Running 3_provide_examples.py...")
        try:
            subprocess.run([sys.executable, "workflows/3_provide_examples.py", "--dataset", config['dataset']], check=True)
        except Exception as e:
            print(f"Error running examples setup: {e}")
            
    # Step 7: Prepare Tables and Run Generation
    print("\n--- Step 7: Prepare Tables and Run Generation ---")
    run_gen = input("Do you want to prepare tables and trigger generation now? (Y/n): ").strip().lower()
    if run_gen == 'y' or run_gen == '':

        print("Running 4_prepare_input_and_output.py...")
        try:
            subprocess.run([sys.executable, "workflows/4_prepare_input_and_output.py", "--dataset", config['dataset']], check=True)
            
            print("Running 5_run_generation.py...")
            subprocess.run([sys.executable, "workflows/5_run_generation.py", "--dataset", config['dataset']], check=True)
            
        except Exception as e:
            print(f"Error during table preparation or generation: {e}")
            
    print("\n=== Wizard Completed ===")

if __name__ == "__main__":
    main()
