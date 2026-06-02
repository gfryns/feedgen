from google.cloud import bigquery

def get_bq_client(project_id: str):
    """Returns an authenticated BigQuery client."""
    return bigquery.Client(project=project_id)

