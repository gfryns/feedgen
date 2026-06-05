from google.cloud import bigquery
from google.cloud import storage
from services.bq_client import get_bq_client
from google.cloud import bigquery_connection_v1
from google.cloud import resourcemanager_v3
import google.auth
import google.iam.v1.iam_policy_pb2 as iam_policy_pb2
import google.iam.v1.policy_pb2 as policy_pb2

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

def create_connection(project_val: str, connection_id: str, region_val: str, bucket_name: str = None, log_cb=print):
    """Creates a BigQuery Cloud Resource Connection and configures IAM policies."""
    log_cb(f"Setting up BigQuery Connection '{connection_id}'...\n")
    
    try:
        credentials, _ = google.auth.default()
        client = bigquery_connection_v1.ConnectionServiceClient(credentials=credentials)
        parent = f"projects/{project_val}/locations/{region_val}"
        conn_name = f"{parent}/connections/{connection_id}"
        
        # 1. Create Connection if not exists
        try:
            conn = client.get_connection(name=conn_name)
            log_cb(f"Connection '{connection_id}' already exists.\n")
        except Exception:
            log_cb(f"Creating CLOUD_RESOURCE connection '{connection_id}' in {region_val}...\n")
            connection = bigquery_connection_v1.Connection(
                friendly_name="FeedGen Cloud Resource Connection",
                description="Used by FeedGen to access external GCS buckets",
                cloud_resource=bigquery_connection_v1.CloudResourceProperties()
            )
            request = bigquery_connection_v1.CreateConnectionRequest(
                parent=parent,
                connection=connection,
                connection_id=connection_id
            )
            conn = client.create_connection(request=request)
            log_cb("Connection created successfully.\n")
            
        sa_id = conn.cloud_resource.service_account_id
        log_cb(f"Connection Service Account: {sa_id}\n")
        member = f"serviceAccount:{sa_id}"
        
        # 2. Grant Vertex AI User on Project
        log_cb(f"Granting roles/aiplatform.user to {sa_id} on project {project_val}...\n")
        rm_client = resourcemanager_v3.ProjectsClient(credentials=credentials)
        project_name = f"projects/{project_val}"
        policy = rm_client.get_iam_policy(resource=project_name)
        
        binding_found = False
        for binding in policy.bindings:
            if binding.role == "roles/aiplatform.user":
                if member not in binding.members:
                    binding.members.append(member)
                binding_found = True
                break
        if not binding_found:
            policy.bindings.append(
                policy_pb2.Binding(
                    role="roles/aiplatform.user",
                    members=[member]
                )
            )
            
        request = iam_policy_pb2.SetIamPolicyRequest(
            resource=project_name,
            policy=policy
        )
        rm_client.set_iam_policy(request=request)
        log_cb("Project IAM policy updated.\n")
        
        # 3. Grant Storage Object Viewer on Bucket (if provided)
        if bucket_name:
            log_cb(f"Granting roles/storage.objectViewer to {sa_id} on bucket {bucket_name}...\n")
            storage_client = storage.Client(project=project_val, credentials=credentials)
            bucket = storage_client.bucket(bucket_name)
            bucket_policy = bucket.get_iam_policy(requested_policy_version=3)
            
            # Add member to roles/storage.objectViewer
            bucket_policy.bindings.append({
                "role": "roles/storage.objectViewer",
                "members": {member}
            })
            bucket.set_iam_policy(bucket_policy)
            log_cb("Bucket IAM policy updated.\n")
            
    except Exception as e:
        log_cb(f"Error setting up connection: {e}\n")
        raise Exception(f"Failed to set up BigQuery connection: {e}")

