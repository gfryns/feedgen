from google.cloud import bigquery
from google.cloud import storage
from services.bq_client import get_bq_client

def create_bucket(project: str, bucket_name: str, region: str, log_cb=print):
    """Creates a new GCS bucket with a 15-day lifecycle rule."""
    storage_client = storage.Client(project=project)
    try:
        bucket = storage_client.get_bucket(bucket_name)
        log_cb(f"Bucket {bucket_name} already exists.\n")
        return
    except Exception:
        pass
        
    log_cb(f"Creating bucket {bucket_name} in {region}...\n")
    bucket = storage_client.bucket(bucket_name)
    bucket.add_lifecycle_delete_rule(age=15)
    storage_client.create_bucket(bucket, location=region)
    log_cb("Bucket created with 15-day lifecycle rule.\n")

def create_dataset(project_val: str, dataset_val: str, region_val: str, log_cb=print):
    """Creates the dataset."""
    client = get_bq_client(project_val)
    
    log_cb(f"Creating dataset {dataset_val} in {region_val}...\n")
    dataset_id = f"{project_val}.{dataset_val}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = region_val
    client.create_dataset(dataset, exists_ok=True)
    log_cb("Dataset created.\n")
