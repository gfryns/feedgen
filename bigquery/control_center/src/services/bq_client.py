import os
import ssl
from google.cloud import bigquery

def get_bq_client(project_id: str, insecure: bool = False):
    """Returns an authenticated BigQuery client."""
    if insecure:
        os.environ['PYTHONHTTPSVERIFY'] = '0'
        ssl._create_default_https_context = ssl._create_unverified_context
    return bigquery.Client(project=project_id)
