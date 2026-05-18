import subprocess

def enable_apis(project_val: str, log_cb=print):
    """Enables the necessary APIs for the given GCP project (Vertex AI, BigQuery, etc.)."""
    log_cb("Starting setup...\n")
    
    apis = [
        "serviceusage.googleapis.com",
        "aiplatform.googleapis.com",
        "bigquery.googleapis.com"
    ]
    
    for api in apis:
        log_cb(f"Enabling {api} for project {project_val}...\n")
        try:
            # Using gcloud CLI as it is more robust for project setup/bootstrapping
            result = subprocess.run(
                ["gcloud", "services", "enable", api, "--project", project_val],
                check=True,
                capture_output=True,
                text=True
            )
            if result.stdout:
                log_cb(result.stdout)
            if result.stderr:
                log_cb(result.stderr)
        except subprocess.CalledProcessError as e:
            log_cb(f"Error enabling {api}: {e.stderr}\n")
            raise Exception(f"Failed to enable {api}: {e.stderr}")
            
    log_cb("Done.\n")
