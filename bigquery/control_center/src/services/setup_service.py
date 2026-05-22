from google.cloud import bigquery
from services.bq_client import get_bq_client

def create_dataset(project_val: str, dataset_val: str, region_val: str, log_cb=print):
    """Creates the dataset."""
    client = get_bq_client(project_val)
    
    log_cb(f"Creating dataset {dataset_val} in {region_val}...\n")
    dataset_id = f"{project_val}.{dataset_val}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = region_val
    client.create_dataset(dataset, exists_ok=True)
    log_cb("Dataset created.\n")
