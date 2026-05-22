from google.cloud import bigquery
from google.cloud import storage
import sys
import os
import json

# Add src to path so we can import services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
from services.generation_service import load_and_merge_results

def main():
    # Read parameters from state.json
    state_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../state.json'))
    print(f"Reading state from {state_path}...")
    try:
        with open(state_path, 'r') as f:
            state = json.load(f)
    except Exception as e:
        print(f"Error reading state.json: {e}")
        return
        
    project = state.get('project')
    dataset = state.get('dataset')
    bucket = state.get('bucket')
    output_table = state.get('output_table')
    
    if not all([project, dataset, bucket, output_table]):
        print("Error: Missing required parameters in state.json")
        return
        
    # Try to read prefixes from state.json
    ongoing = state.get('ongoing_generation', {})
    prefixes = ongoing.get('prefixes', {})
    
    if prefixes:
        print(f"Found ongoing generation prefixes in state.json: {prefixes}")
        target_prefixes = prefixes
    else:
        print("No ongoing generation prefixes found in state.json. Using hardcoded examples.")
        # IMPORTANT: Fill these with the actual prefixes found in your GCS bucket
        # Example: "output/output_titles/prediction-model-2026-05-22T13:51:18.421986Z/"
        target_prefixes = {
            "Titles": "output/output_titles/prediction-model-2026-05-22T16:23:46.633407Z/",
            "Descriptions": "output/output_descriptions/prediction-model-2026-05-22T16:23:52.160621Z/"
        }
    
    print("Initializing clients...")
    storage_client = storage.Client(project=project)
    bq_client = bigquery.Client(project=project)
    
    print(f"Starting merge for project={project}, dataset={dataset}, table={output_table}")
    try:
        load_and_merge_results(
            project=project,
            dataset=dataset,
            bucket=bucket,
            output_table=output_table,
            target_prefixes=target_prefixes,
            log_cb=print,
            storage_client=storage_client,
            client=bq_client
        )
        print("Merge completed successfully!")
    except Exception as e:
        print(f"Error during merge: {e}")

if __name__ == "__main__":
    main()
