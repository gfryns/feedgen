import argparse
import csv
import os
import time
from bs4 import BeautifulSoup
from google.cloud import bigquery
import requests

# Default configurations
DEFAULT_DATASET = "feedgen_dataset"
DEFAULT_SOURCE_TABLE = "InputFiltered"
DEFAULT_DEST_TABLE = "InputFilteredWeb"
DEFAULT_URL_COLUMN = "link"
DEFAULT_ID_COLUMN = "id"
DEFAULT_SELECTOR = 'div[data-testid^="item-description"]'
DEFAULT_SLEEP = 0.5

def main():
    parser = argparse.ArgumentParser(description="Parse product descriptions from webpages.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="BigQuery dataset name")
    parser.add_argument("--source_table", default=DEFAULT_SOURCE_TABLE, help="Source table name")
    parser.add_argument("--dest_table", default=DEFAULT_DEST_TABLE, help="Destination table name")
    parser.add_argument("--url_column", default=DEFAULT_URL_COLUMN, help="Column containing URLs")
    parser.add_argument("--id_column", default=DEFAULT_ID_COLUMN, help="Column containing IDs")
    parser.add_argument("--selector", default=DEFAULT_SELECTOR, help="CSS selector for description elements")
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP, help="Sleep time between requests in seconds")
    
    args = parser.parse_args()
    
    client = bigquery.Client()
    
    query = f"SELECT {args.id_column}, {args.url_column} FROM `{client.project}.{args.dataset}.{args.source_table}`"
    print(f"Running query: {query}")
    
    query_job = client.query(query)
    results = query_job.result()
    
    csv_filename = "ids_contents.csv"
    
    print(f"Writing temporary results to {csv_filename}")
    with open(csv_filename, mode='w', newline='', encoding='utf-8') as csv_file:
        fieldnames = ['id', 'content']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        
        # No header written, matching original behavior for bq load
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        for row in results:
            item_id = row[args.id_column]
            url = row[args.url_column]
            
            print(f"Fetching: {url} (ID: {item_id})")
            
            content = ""
            try:
                if args.sleep > 0:
                    time.sleep(args.sleep)
                
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                elements = soup.select(args.selector)
                content = " ".join(el.get_text() for el in elements)
                
                # Clean content: remove newlines and extra spaces
                content = content.replace('\n', ' ').replace('\r', '').strip()
                content = " ".join(content.split()) # Normalize whitespace
                
            except Exception as e:
                print(f"Error fetching/parsing {url}: {e}")
                # We continue even if it fails, content will be empty
                
            writer.writerow({'id': item_id, 'content': content})
            
    # Load to BigQuery
    table_id = f"{client.project}.{args.dataset}.{args.dest_table}"
    
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=0,
        schema=[
            bigquery.SchemaField("id", "STRING"),
            bigquery.SchemaField("content", "STRING"),
        ],
        write_disposition="WRITE_TRUNCATE",
    )
    
    print(f"Loading data from {csv_filename} to {table_id}")
    with open(csv_filename, "rb") as source_file:
        load_job = client.load_table_from_file(source_file, table_id, job_config=job_config)
        
    print(f"Starting job {load_job.job_id}")
    load_job.result()  # Waits for the job to complete.
    print(f"Job finished. Loaded data to {table_id}")
    
    # Clean up
    if os.path.exists(csv_filename):
        os.remove(csv_filename)
        print(f"Cleaned up {csv_filename}")

if __name__ == "__main__":
    main()
