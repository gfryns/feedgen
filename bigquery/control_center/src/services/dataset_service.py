from google.cloud import bigquery
from google.cloud import bigquery_connection_v1 as bq_connection
from google.cloud import resourcemanager_v3
from google.iam.v1 import policy_pb2
import time
from services.bq_client import get_bq_client

def deploy_dataset_and_model(project_val: str, dataset_val: str, region_val: str, connection_val: str, model_val: str, titles_prompt_path: str = "prompts/titles.txt", desc_prompt_path: str = "prompts/descriptions.txt", log_cb=print):
    """Creates the dataset, connection, model, IAM bindings, and routines."""
    client = get_bq_client(project_val)
    
    # 1. Create Dataset
    log_cb(f"Creating dataset {dataset_val} in {region_val}...\n")
    dataset_id = f"{project_val}.{dataset_val}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = region_val
    client.create_dataset(dataset, exists_ok=True)
    
    # 2. Create Connection
    log_cb(f"Creating connection {connection_val}...\n")
    conn_client = bq_connection.ConnectionServiceClient()
    parent = conn_client.common_location_path(project_val, region_val)
    connection = bq_connection.Connection(
        cloud_resource=bq_connection.CloudResourceProperties()
    )
    request = bq_connection.CreateConnectionRequest(
        parent=parent,
        connection_id=connection_val,
        connection=connection
    )
    try:
        conn = conn_client.create_connection(request=request)
    except Exception as e:
        if 'Already exists' in str(e) or '409' in str(e):
            request_get = bq_connection.GetConnectionRequest(name=f"{parent}/connections/{connection_val}")
            conn = conn_client.get_connection(request=request_get)
        else:
            raise e
    
    # 3. Get Service Account
    log_cb("Fetching service account...\n")
    sa = conn.cloud_resource.service_account_id
    log_cb(f"Service Account: {sa}\n")
    
    # 4. Grant IAM role
    log_cb("Granting IAM role to service account...\n")
    rm_client = resourcemanager_v3.ProjectsClient()
    project_name = f"projects/{project_val}"
    
    policy = rm_client.get_iam_policy(resource=project_name)
    
    role = "roles/aiplatform.user"
    member = f"serviceAccount:{sa}"
    binding_exists = False
    member_exists = False

    for binding in policy.bindings:
        if binding.role == role:
            binding_exists = True
            if member in binding.members:
                member_exists = True
            else:
                binding.members.append(member)
            break

    if not binding_exists:
        new_binding = policy_pb2.Binding(role=role, members=[member])
        policy.bindings.append(new_binding)

    if not member_exists:
        # Set policy using the correct request structure
        from google.iam.v1 import iam_policy_pb2
        request_set_iam = iam_policy_pb2.SetIamPolicyRequest(resource=project_name, policy=policy)
        rm_client.set_iam_policy(request=request_set_iam)

        log_cb("Waiting 30 seconds for IAM permissions to propagate...\n")
        time.sleep(30)
    else:
        log_cb("IAM role already granted. Skipping delay.\n")
    sql_model = f"""
    CREATE OR REPLACE MODEL `{project_val}.{dataset_val}.GeminiModel`
      REMOTE WITH CONNECTION `{project_val}.{region_val}.{connection_val}`
      OPTIONS (endpoint = '{model_val}');
    """
    client.query(sql_model).result()
    log_cb("Model created.\n")
    
    # 6. Deploy Procedures
    log_cb("Installing stored functions and procedures...\n")
    with open("generation.sql", "r") as f:
        gen_sql = f.read()
        
    with open(titles_prompt_path, "r") as f:
        titles_prompt = f.read()
    with open(desc_prompt_path, "r") as f:
        descriptions_prompt = f.read()
        
    gen_sql = gen_sql.replace("[DATASET]", f"{project_val}.{dataset_val}")
    gen_sql = gen_sql.replace("[OUTPUT_TABLE]", f"{project_val}.{dataset_val}.Output")
    gen_sql = gen_sql.replace("-- TITLES_PROMPT", titles_prompt)
    gen_sql = gen_sql.replace("-- DESCRIPTIONS_PROMPT", descriptions_prompt)

    client.query(gen_sql).result()
    log_cb("Functions and procedures installed.\n")
