import asyncio
import concurrent.futures
import hashlib
import requests
import certifi
from google.cloud import storage
from google.cloud import bigquery
from services.bq_client import get_bq_client

def get_bucket_stats(project: str, bucket_name: str):
    """Returns the number of images and total size in the bucket."""
    storage_client = storage.Client(project=project)
    try:
        bucket = storage_client.get_bucket(bucket_name)
        blobs = list(bucket.list_blobs(prefix="images/"))
        count = len(blobs)
        total_size = sum(blob.size for blob in blobs)
        return count, total_size
    except Exception:
        return None, None

def create_bucket(project: str, bucket_name: str, region: str):
    """Creates a new GCS bucket."""
    storage_client = storage.Client(project=project)
    storage_client.create_bucket(bucket_name, location=region)

def delete_images(project: str, dataset: str, bucket_name: str, progress_cb=None, is_cancelled=lambda: False):
    """Deletes all images in the bucket and drops the external table."""
    storage_client = storage.Client(project=project)
    bucket = storage_client.get_bucket(bucket_name)
    
    # Fetch blobs first
    blobs_list = list(bucket.list_blobs(prefix="images/"))
    
    if progress_cb:
        progress_cb(total=len(blobs_list), progress=0)
        
    count = 0
    from google.api_core.exceptions import NotFound
    for blob in blobs_list:
        if is_cancelled(): break
        try:
            blob.delete()
            count += 1
        except NotFound:
            pass
        if progress_cb:
            progress_cb(advance=1)
            
    # Drop table
    client = get_bq_client(project)
    sql_drop = f"DROP TABLE IF EXISTS `{project}.{dataset}.Images`"
    client.query(sql_drop).result()
    
    return count

def run_image_processing(project: str, dataset: str, bucket_name: str, connection_val: str, region_val: str, img_url_col: str, log_cb=print, progress_cb=None, is_cancelled=lambda: False):
    """Downloads images and creates an external table in BigQuery."""
    storage_client = storage.Client(project=project)
    bucket = storage_client.get_bucket(bucket_name)
    
    client = get_bq_client(project)
    
    table_ref = client.get_table(f"{project}.{dataset}.InputFiltered")
    schema_names = [f.name for f in table_ref.schema]
    actual_img_url_col = 'image_url' if 'image_url' in schema_names else img_url_col

    query = f"SELECT DISTINCT {actual_img_url_col} FROM `{project}.{dataset}.InputFiltered` WHERE {actual_img_url_col} IS NOT NULL"
    log_cb(f"Fetching image URLs...\n")
    
    results = list(client.query(query).result())
    urls = [row[actual_img_url_col] for row in results]
    log_cb(f"Found {len(urls)} unique image URLs.\n")
    
    log_cb("Analyzing existing images in bucket...\n")
    existing_blobs = set(b.name for b in bucket.list_blobs(prefix="images/"))
    log_cb(f"Found {len(existing_blobs)} existing images. Processing remaining...\n")
    
    if progress_cb:
        progress_cb(total=len(urls), progress=0)
        
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    success_count = 0
    skipped_count = 0
    
    def process_image(url):
        if is_cancelled(): return False, "cancelled", ""
        
        filename = url.split('/')[-1]
        if not filename or '?' in filename:
            filename = f"image_{hashlib.md5(url.encode()).hexdigest()}.jpg"
            
        blob_path = f"images/{filename}"
        
        if blob_path in existing_blobs:
            return True, "skipped", filename
            
        blob = bucket.blob(blob_path)
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=10, verify=certifi.where())
            response.raise_for_status()
            blob.upload_from_file(response.raw, content_type=response.headers.get('Content-Type', 'image/jpeg'))
            return True, "uploaded", filename
        except Exception as e:
            return False, f"Error {url}: {e}", filename

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_url = {executor.submit(process_image, url): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            if is_cancelled():
                executor.shutdown(wait=False, cancel_futures=True)
                return {'cancelled': True}
            
            success, status, filename = future.result()
            if success:
                if status == "skipped":
                    skipped_count += 1
                else:
                    success_count += 1
                    log_cb(f"Success: uploaded {filename}\n")
            else:
                if status != "cancelled":
                    log_cb(f"{status}\n")
            
            if progress_cb:
                progress_cb(advance=1)
                
    log_cb(f"Finished: {success_count} uploaded, {skipped_count} skipped.\n")
    log_cb("Creating external table in BigQuery...\n")
    
    connection_path = f"{project}.{region_val.lower()}.{connection_val}"
    
    sql_external = f"""
    CREATE OR REPLACE EXTERNAL TABLE `{project}.{dataset}.Images`
    WITH CONNECTION `{connection_path}`
    OPTIONS(
      object_metadata = 'SIMPLE',
      uris = ['gs://{bucket_name}/images/*'],
      max_staleness = INTERVAL 7 DAY,
      metadata_cache_mode = 'AUTOMATIC');
    """
    
    client.query(sql_external).result()
    log_cb("External table 'Images' created.\n")
    
    return {
        'total': len(urls),
        'success': success_count,
        'skipped': skipped_count
    }
