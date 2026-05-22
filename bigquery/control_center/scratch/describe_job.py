from google.cloud import aiplatform
import sys

def main():
    project = "test-gfryns"
    location = "global"
    job_id = "8340800100552933376"
    
    if len(sys.argv) > 1:
        job_id = sys.argv[1]
        
    aiplatform.init(project=project, location=location)
    try:
        res_name = f"projects/420681460512/locations/global/batchPredictionJobs/{job_id}"
        print(f"Fetching job: {res_name}")
        job = aiplatform.BatchPredictionJob(res_name)
        print(f"Job State: {job.state.name}")
        print(f"Display Name: {job.display_name}")
        import pprint
        pprint.pprint(job.to_dict())
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
