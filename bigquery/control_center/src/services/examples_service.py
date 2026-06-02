import asyncio
import json
import uuid
from services.bq_client import get_bq_client
from google.cloud import bigquery

def get_examples_preview(project: str, dataset: str):
    """Returns the count and a preview of top 5 examples."""
    client = get_bq_client(project)
    table_id = f"{project}.{dataset}.Examples"
    
    try:
        # Get count
        count_query = f"SELECT COUNT(*) as total FROM `{table_id}`"
        count_res = list(client.query(count_query).result())
        total_count = count_res[0]['total'] if count_res else 0
        
        # Get top 5 rows
        query = f"SELECT id, title, description FROM `{table_id}` LIMIT 5"
        res = list(client.query(query).result())
        
        preview_data = [
            (str(row['id']), str(row['title']), str(row['description'])) 
            for row in res
        ]
        
        return total_count, preview_data
    except Exception:
        return 0, []

def load_examples_from_sheet(project: str, dataset: str, url: str, sheet_name: str, range_val: str, has_header: bool, log_cb=print):
    """Loads examples from a Google Sheet into BigQuery."""
    import gspread
    import google.auth
    
    log_cb("Authenticating with Google Sheets...\n")
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets'])
    gc = gspread.authorize(credentials)
    
    log_cb("Opening spreadsheet...\n")
    sh = gc.open_by_url(url)
    worksheet = sh.worksheet(sheet_name)
    
    log_cb("Fetching data...\n")
    if range_val:
        values = worksheet.get(range_val)
    else:
        values = worksheet.get_all_values()
        
    if not values:
        raise ValueError("No data found in the sheet.")
        
    if has_header:
        headers = values[0]
        rows = values[1:]
    else:
        headers = ['properties', 'title', 'description']
        rows = values
        
    log_cb(f"Read {len(rows)} rows from sheet.\n")
    
    prop_idx = headers.index('properties') if 'properties' in headers else 0
    title_idx = headers.index('title') if 'title' in headers else 1
    desc_idx = headers.index('description') if 'description' in headers else 2
    
    examples = []
    for row in rows:
        if len(row) <= max(prop_idx, title_idx, desc_idx):
            continue
        props = row[prop_idx].strip()
        title = row[title_idx].strip()
        desc = row[desc_idx].strip()
        
        if not props and not title and not desc:
            continue
            
        try:
            json.loads(props)
        except json.JSONDecodeError:
            log_cb(f"Warning: Invalid JSON in row: {props}. Skipping.\n")
            continue
            
        examples.append({
            'id': str(uuid.uuid4()),
            'properties': props,
            'title': title,
            'description': desc
        })
        
    if not examples:
        raise ValueError("No valid examples found.")
        
    client = get_bq_client(project)
    table_id = f"{project}.{dataset}.Examples"
    
    job_config = bigquery.LoadJobConfig(
        schema=[
            bigquery.SchemaField("id", "STRING"),
            bigquery.SchemaField("properties", "STRING"),
            bigquery.SchemaField("title", "STRING"),
            bigquery.SchemaField("description", "STRING"),
        ],
        write_disposition="WRITE_TRUNCATE",
    )
    
    log_cb(f"Loading {len(examples)} examples to {table_id}...\n")
    job = client.load_table_from_json(examples, table_id, job_config=job_config)
    job.result()
    
    log_cb("Examples loaded successfully.\n")
    return len(examples)

def load_examples_by_ids(project: str, dataset: str, source: str, ids_str: str, log_cb=print):
    """Loads specific examples by ID from a source table."""
    ids = [i.strip() for i in ids_str.split(',') if i.strip()]
    if not ids:
        raise ValueError("No IDs provided.")
        
    client = get_bq_client(project)
    table_id = f"{project}.{dataset}.Examples"
    
    ids_formatted = ", ".join([f"'{i}'" for i in ids])
    
    if '.' in source:
        parts = source.split('.')
        source_ref = ".".join([f"`{p}`" for p in parts])
    else:
        source_ref = f"`{project}.{dataset}.{source}`"
        
    verify_query = f"SELECT id FROM {source_ref} WHERE id IN ({ids_formatted})"
    log_cb(f"Verifying IDs with query: {verify_query}\n")
    
    found_res = list(client.query(verify_query).result())
    found_ids = [row['id'] for row in found_res]
    
    missing_ids = set(ids) - set(found_ids)
    if missing_ids:
        log_cb(f"Warning: The following IDs were not found: {list(missing_ids)}\n")
        
    if not found_ids:
        raise ValueError("None of the provided IDs were found in the source table.")
        
    ids_formatted = ", ".join([f"'{i}'" for i in found_ids])
    
    sql = f"""
    CREATE OR REPLACE TABLE `{table_id}` AS
    SELECT
      id,
      TO_JSON_STRING((SELECT AS STRUCT * EXCEPT(id) FROM UNNEST([I]))) AS properties,
      title,
      description
    FROM {source_ref} AS I
    WHERE id IN ({ids_formatted})
    """
    
    log_cb(f"Executing SQL:\n{sql}\n")
    client.query(sql).result()
    log_cb("Examples created successfully.\n")
    
    return len(found_ids), list(missing_ids)

def clear_examples(project: str, dataset: str):
    """Deletes the Examples table."""
    client = get_bq_client(project)
    table_id = f"{project}.{dataset}.Examples"
    client.delete_table(table_id, not_found_ok=True)
