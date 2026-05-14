import argparse
import os
import time
from google.cloud import bigquery
from google.cloud import storage
import requests

# Default configurations
DEFAULT_DATASET = "feedgen_dataset"
DEFAULT_SOURCE_TABLE = "InputFiltered"
DEFAULT_DEST_TABLE = "InputFilteredImages"
DEFAULT_EXTERNAL_TABLE = "Images"
DEFAULT_URL_COLUMN = "image_link"
DEFAULT_MODEL = "GeminiModel"

def main():
    parser = argparse.ArgumentParser(description="Process images for BigQuery and generate descriptions.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="BigQuery dataset name")
    parser.add_argument("--source_table", default=DEFAULT_SOURCE_TABLE, help="Source table name containing image URLs")
    parser.add_argument("--dest_table", default=DEFAULT_DEST_TABLE, help="Destination table name for descriptions")
    parser.add_argument("--external_table", default=DEFAULT_EXTERNAL_TABLE, help="Name of the external object table to create")
    parser.add_argument("--url_column", default=DEFAULT_URL_COLUMN, help="Column name containing image URLs")
    parser.add_argument("--bucket", required=True, help="GCS Bucket name to upload images to")
    parser.add_argument("--connection", required=True, help="BigQuery connection name (full path or name if in same project/location)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="BigQuery ML model name")
    parser.add_argument("--sleep", type=float, default=0.5, help="Sleep time between requests in seconds")
    
    args = parser.parse_args()
    
    bq_client = bigquery.Client()
    storage_client = storage.Client()
    
    # Guess location from dataset
    try:
        dataset_ref = bq_client.get_dataset(args.dataset)
        location = dataset_ref.location
        print(f"Inferred location for dataset {args.dataset}: {location}")
    except Exception as e:
        print(f"Could not infer dataset location: {e}. Defaulting to 'us'.")
        location = "us"
        
    # Create bucket if missing
    try:
        bucket = storage_client.get_bucket(args.bucket)
        print(f"Bucket {args.bucket} exists.")
    except Exception as e:
        print(f"Bucket {args.bucket} not found. Trying to create it...")
        try:
            # Create bucket in the inferred location
            bucket = storage_client.create_bucket(args.bucket, location=location)
            print(f"Created bucket {args.bucket} in location {location}")
        except Exception as ce:
            print(f"Failed to create bucket: {ce}")
            # We will likely fail later if it doesn't exist, but we proceed.
            bucket = storage_client.bucket(args.bucket)
            
    # 1. Query for image URLs
    query = f"SELECT DISTINCT {args.url_column} FROM `{bq_client.project}.{args.dataset}.{args.source_table}`"
    print(f"Running query: {query}")
    
    query_job = bq_client.query(query)
    results = query_job.result()
    
    bucket = storage_client.bucket(args.bucket)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    from tqdm import tqdm
    for row in tqdm(results, total=results.total_rows, desc="Processing images"):
        url = row[args.url_column]
        if not url:
            continue
            
        tqdm.write(f"Processing: {url}")
        
        # Extract filename from URL or use a hash
        filename = url.split('/')[-1]
        if not filename or '?' in filename:
            # Fallback if filename is not clear or contains query params
            filename = f"image_{hash(url)}.jpg"
            
        blob = bucket.blob(f"images/{filename}")
        
        try:
            if args.sleep > 0:
                time.sleep(args.sleep)
                
            # Stream directly to GCS
            response = requests.get(url, headers=headers, stream=True, timeout=10)
            response.raise_for_status()
            
            # Upload from stream
            blob.upload_from_file(response.raw, content_type=response.headers.get('Content-Type', 'image/jpeg'))
            tqdm.write(f"Uploaded to gs://{args.bucket}/images/{filename}")
            
        except Exception as e:
            tqdm.write(f"Error downloading/uploading {url}: {e}")
            
    # 3. Create External Table
    # We assume connection is in the same project and location 'us' if not fully qualified
    connection_path = args.connection
    if '.' not in connection_path:
        connection_path = f"{bq_client.project}.{location.lower()}.{args.connection}"
        
    sql_create_external = f"""
    CREATE OR REPLACE EXTERNAL TABLE `{bq_client.project}.{args.dataset}.{args.external_table}`
    WITH CONNECTION `{connection_path}`
    OPTIONS(
      object_metadata = 'SIMPLE',
      uris = ['gs://{args.bucket}/images/*'],
      max_staleness = INTERVAL 7 DAY,
      metadata_cache_mode = 'AUTOMATIC');
    """
    
    print("Creating external table...")
    try:
        bq_client.query(sql_create_external).result()
        print("External table created.")
    except Exception as e:
        print(f"Error creating external table: {e}")
        
    # 4. Describe images
    sql_describe = f"""
    CREATE OR REPLACE TABLE `{bq_client.project}.{args.dataset}.{args.dest_table}` AS
    SELECT uri, TRIM(ml_generate_text_llm_result) AS description
    FROM
      ML.GENERATE_TEXT(
        MODEL `{bq_client.project}.{args.dataset}`.`{args.model}`,
        TABLE `{bq_client.project}.{args.dataset}.{args.external_table}`,
        STRUCT(
          'Provide a detailed description of the product shown on this image, including any visible text.' AS prompt,
          0 AS temperature,
          1024 AS max_output_tokens,
          TRUE AS flatten_json_output));
    """
    
    print("Generating descriptions in a single batch for efficiency. This may take a while... Please wait.")
    try:
        bq_client.query(sql_describe).result()
        print("Descriptions generated.")
    except Exception as e:
        print(f"Error generating descriptions: {e}")

if __name__ == "__main__":
    main()
