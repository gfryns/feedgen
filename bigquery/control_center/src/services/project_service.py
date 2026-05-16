from google.cloud import service_usage_v1

def enable_vertex_ai(project_val: str, log_cb=print):
    """Enables the Vertex AI API for the given GCP project."""
    log_cb("Starting setup...\n")
    client = service_usage_v1.ServiceUsageClient()
    
    log_cb(f"Setting active project: {project_val}\n")
    log_cb(f"Enabling Vertex AI API for project {project_val}...\n")
    
    service_name = f"projects/{project_val}/services/aiplatform.googleapis.com"
    request = service_usage_v1.EnableServiceRequest(name=service_name)
    
    operation = client.enable_service(request=request)
    operation.result() # Wait for completion
    
    log_cb("Done.\n")
