import argparse
import json
import os
import re
import subprocess
import sys
from google.cloud import bigquery

# Default configurations
DEFAULT_DATASET = "feedgen_dataset"
CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def get_dataset(default_dataset):
    dataset = input(f"Enter BigQuery dataset name (default: {default_dataset}): ").strip()
    return dataset if dataset else default_dataset

def main():
    parser = argparse.ArgumentParser(description="Provide Examples Script")
    parser.add_argument("--dataset", help="BigQuery dataset name")
    args = parser.parse_args()
    
    config = load_config()
    default_dataset = args.dataset if args.dataset else config.get('dataset', DEFAULT_DATASET)
    
    print("--- Provide Examples Script ---")
    
    try:
        client = bigquery.Client(project=config.get('project'))
    except Exception as e:
        print(f"Error initializing BigQuery client: {e}")
        print("Make sure you have active credentials.")
        sys.exit(1)
        
    dataset = get_dataset(default_dataset)
    table_id = f"{client.project}.{dataset}.Examples"
    
    while True:
        print("\nHow do you want to manage examples?")
        print("1. Load examples from Google Spreadsheet")
        print("2. Pick specific products from the existing feed by ID (using their existing titles/descriptions)")
        print("3. Pick top-performing products from the feed based on a metric")
        print("4. Delete all existing examples (clear table)")
        print("5. Exit")
        
        choice = input("Enter your choice (1-5): ").strip()
        
        if choice == '1':
            fallback = handle_option_1(client, table_id, config, dataset)
            if not fallback:
                break
        elif choice == '2':
            handle_option_2(client, table_id, dataset)
            break
        elif choice == '3':
            handle_option_3(client, table_id, dataset)
            break
        elif choice == '4':
            print(f"Deleting table {table_id}...")
            try:
                client.delete_table(table_id, not_found_ok=True)
                print("Examples deleted.")
            except Exception as e:
                print(f"Error deleting table: {e}")
            break
        elif choice == '5':
            print("Exiting.")
            break
        else:
            print("Invalid choice.")

def handle_option_1(client, table_id, config, dataset):
    while True:
        print("\n--- Option 1: Load from Google Spreadsheet ---")
        
        url = input("Enter Google Spreadsheet URL: ").strip()
        if not url:
            print("URL is required.")
            continue
            
        sheet_name = input("Enter Sheet Name (e.g., Sheet1): ").strip()
        if not sheet_name:
            print("Sheet Name is required.")
            continue
            
        range_val = input("Enter Range (optional, e.g., A1:C10, leave blank for all): ").strip()
        
        has_header = input("Does the sheet have a header row? (Y/n): ").strip().lower()
        has_header = has_header != 'n'
        
        print("Authenticating with Google Sheets using your default credentials...")
        try:
            import gspread
            import uuid
            import google.auth
            
            credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets'])
            gc = gspread.authorize(credentials)
            
            print("Opening spreadsheet...")
            sh = gc.open_by_url(url)
            worksheet = sh.worksheet(sheet_name)
            
            print("Fetching data...")
            if range_val:
                values = worksheet.get(range_val)
            else:
                values = worksheet.get_all_values()
                
            if not values:
                print("No data found in the sheet.")
                continue
                
            if has_header:
                headers = values[0]
                rows = values[1:]
            else:
                headers = ['properties', 'title', 'description']
                rows = values
                
            print(f"Read {len(rows)} rows from sheet.")
            
            prop_idx = 0
            title_idx = 1
            desc_idx = 2
            
            if has_header:
                try:
                    prop_idx = headers.index('properties')
                    title_idx = headers.index('title')
                    desc_idx = headers.index('description')
                except ValueError:
                    print("Warning: Could not find 'properties', 'title', or 'description' in headers. Assuming order: properties, title, description.")
                    
            examples = []
            for row in rows:
                if len(row) <= max(prop_idx, title_idx, desc_idx):
                    continue # Skip incomplete rows
                    
                props = row[prop_idx].strip()
                title = row[title_idx].strip()
                desc = row[desc_idx].strip()
                
                # Filter blank rows
                if not props and not title and not desc:
                    continue
                    
                # Validate JSON
                try:
                    json.loads(props)
                except json.JSONDecodeError:
                    print(f"Warning: Invalid JSON in row: {props}. Skipping.")
                    continue
                    
                examples.append({
                    'id': str(uuid.uuid4()),
                    'properties': props,
                    'title': title,
                    'description': desc
                })
                
            if not examples:
                print("No valid examples found.")
                continue
                
            # Load to BigQuery
            job_config = bigquery.LoadJobConfig(
                schema=[
                    bigquery.SchemaField("id", "STRING"),
                    bigquery.SchemaField("properties", "STRING"),
                    bigquery.SchemaField("title", "STRING"),
                    bigquery.SchemaField("description", "STRING"),
                ],
                write_disposition="WRITE_TRUNCATE",
            )
            
            print(f"Loading {len(examples)} examples to BigQuery...")
            job = client.load_table_from_json(examples, table_id, job_config=job_config)
            job.result()
            print(f"Table {table_id} created successfully with {len(examples)} examples.")
            
            return False # Success, don't retry main menu
            
        except Exception as e:
            import gspread
            if isinstance(e, gspread.exceptions.APIError) and ('insufficient authentication scopes' in str(e).lower() or (getattr(e, 'response', None) and e.response.status_code == 403)):
                print("\n[ERROR] Request had insufficient authentication scopes.")
                print("To fix this, you need to run:")
                print("gcloud auth application-default login --scopes=https://www.googleapis.com/auth/drive,https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/cloud-platform")
                
                choice = input("\nWhat do you want to do?\n1. Try again\n2. Pick another option\nEnter choice (1-2): ").strip()
                if choice == '1':
                    continue # Retry handle_option_1 loop
                elif choice == '2':
                    return True # Signal fallback to main menu
                else:
                    print("Invalid choice. Returning to main menu.")
                    return True
            else:
                import traceback
                print("Error processing spreadsheet:")
                traceback.print_exc()
                print("Make sure you have access to the spreadsheet and the range is correct.")
                return False # Error, but don't retry menu automatically

def handle_option_2(client, table_id, dataset):
    source_table = input("Enter source table name (default: InputProcessing): ").strip()
    if not source_table:
        source_table = "InputProcessing"
        
    # Show some examples
    query_examples = f"SELECT id FROM `{client.project}.{dataset}.{source_table}` LIMIT 3"
    print(f"Fetching sample IDs from {source_table}...")
    try:
        results = client.query(query_examples).result()
        print("Sample IDs available in table:")
        for row in results:
            print(f"  - {row.id}")
    except Exception as e:
        print(f"Could not fetch samples (maybe table is empty or missing): {e}")
        
    ids_input = input("Enter Product IDs to use as examples (comma-separated): ").strip()
    if not ids_input:
        print("No IDs provided.")
        return
        
    ids = [i.strip() for i in ids_input.split(',')]
    
    # Verify they exist
    ids_str = ", ".join([f"'{i}'" for i in ids])
    query_verify = f"SELECT id FROM `{client.project}.{dataset}.{source_table}` WHERE id IN ({ids_str})"
    
    print("Verifying IDs...")
    try:
        results = client.query(query_verify).result()
        found_ids = [row.id for row in results]
        
        missing_ids = set(ids) - set(found_ids)
        if missing_ids:
            print(f"Warning: The following IDs were not found: {missing_ids}")
            proceed = input("Do you want to proceed with the found IDs only? (y/n): ").strip().lower()
            if proceed != 'y':
                return
            ids = found_ids
            
        if not ids:
            print("No valid IDs to process.")
            return
            
        ids_str = ", ".join([f"'{i}'" for i in ids])
        
        sql = f"""
        CREATE OR REPLACE TABLE `{table_id}` AS
        SELECT
          id,
          TO_JSON_STRING((SELECT AS STRUCT * EXCEPT(id) FROM UNNEST([I]))) AS properties,
          title,
          description
        FROM `{client.project}.{dataset}.{source_table}` AS I
        WHERE id IN ({ids_str})
        """
        
        print(f"Creating Examples table at {table_id}...")
        client.query(sql).result()
        print("Table created successfully with selected products.")
    except Exception as e:
        print(f"Error executing query: {e}")

def handle_option_3(client, table_id, dataset):
    source_table = input("Enter source table name containing metrics (default: InputRaw): ").strip()
    if not source_table:
        source_table = "InputRaw"
        
    metric_col = input("Enter metric column name (e.g., clicks): ").strip()
    if not metric_col:
        print("Metric column is required.")
        return
        
    limit = input("Enter limit (default: 3): ").strip()
    if not limit:
        limit = "3"
        
    sql = f"""
    CREATE OR REPLACE TABLE `{table_id}` AS
    SELECT
      id,
      TO_JSON_STRING((SELECT AS STRUCT * EXCEPT(id) FROM UNNEST([I]))) AS properties,
      title,
      description
    FROM `{client.project}.{dataset}.{source_table}` AS I
    ORDER BY {metric_col} DESC
    LIMIT {limit}
    """
    
    print(f"Creating Examples table at {table_id}...")
    try:
        client.query(sql).result()
        print(f"Table created successfully with top {limit} products based on {metric_col}.")
    except Exception as e:
        print(f"Error creating table: {e}")



if __name__ == "__main__":
    main()
