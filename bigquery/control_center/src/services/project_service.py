from google.cloud import service_usage_v1
import google.auth

def enable_apis(project_val: str, log_cb=print):
    """Enables the necessary APIs for the given GCP project (Vertex AI, BigQuery, etc.)."""
    log_cb("Starting setup...\n")
    
    apis = [
        "serviceusage.googleapis.com",
        "aiplatform.googleapis.com",
        "bigquery.googleapis.com",
        "bigqueryconnection.googleapis.com",
        "cloudresourcemanager.googleapis.com"
    ]
    
    log_cb(f"Enabling APIs: {', '.join(apis)} for project {project_val}...\n")
    try:
        credentials, _ = google.auth.default()
        client = service_usage_v1.ServiceUsageClient(credentials=credentials)
        
        request = service_usage_v1.BatchEnableServicesRequest(
            parent=f"projects/{project_val}",
            service_ids=apis
        )
        
        operation = client.batch_enable_services(request=request)
        log_cb("Waiting for GCP Service Usage operation to complete...\n")
        operation.result()
        log_cb("APIs enabled successfully.\n")
    except Exception as e:
        log_cb(f"Error enabling APIs: {e}\n")
        raise Exception(f"Failed to enable APIs: {e}")
        
    log_cb("Done.\n")
