import argparse
import sys
import time
from google.cloud import bigquery

# Default configurations
DEFAULT_DATASET = "feedgen_dataset"
DEFAULT_LANGUAGE = "German"
DEFAULT_BATCH_SIZE = 15
DEFAULT_WORKERS = 1

def get_dataset():
    dataset = input(f"Enter BigQuery dataset name (default: {DEFAULT_DATASET}): ").strip()
    return dataset if dataset else DEFAULT_DATASET

def main():
    parser = argparse.ArgumentParser(description="Generate Content Script")
    parser.add_argument("--dataset", help="BigQuery dataset name")
    args = parser.parse_args()
    
    print("--- Generate Content Script ---")
    
    try:
        client = bigquery.Client()
    except Exception as e:
        print(f"Error initializing BigQuery client: {e}")
        print("Make sure you have active credentials.")
        sys.exit(1)
        
    if args.dataset:
        dataset = args.dataset
    else:
        dataset = get_dataset()
    
    language = input(f"Enter language (default: {DEFAULT_LANGUAGE}): ").strip()
    if not language:
        language = DEFAULT_LANGUAGE
        
    batch_size = input(f"Enter batch size (items per prompt, default: {DEFAULT_BATCH_SIZE}): ").strip()
    if not batch_size:
        batch_size = DEFAULT_BATCH_SIZE
    else:
        try:
            batch_size = int(batch_size)
        except ValueError:
            print("Invalid number. Using default.")
            batch_size = DEFAULT_BATCH_SIZE
        
    workers = input(f"Enter number of parallel workers (default: {DEFAULT_WORKERS}): ").strip()
    if not workers:
        workers = DEFAULT_WORKERS
    else:
        try:
            workers = int(workers)
        except ValueError:
            print("Invalid number. Using default.")
            workers = DEFAULT_WORKERS
        
    print("\nWhat do you want to generate?")
    print("1. Titles")
    print("2. Descriptions")
    print("3. Both")
    
    choice = input("Enter your choice (1-3): ").strip()
    
    targets = []
    if choice == '1':
        targets = ['Titles']
    elif choice == '2':
        targets = ['Descriptions']
    elif choice == '3':
        targets = ['Descriptions', 'Titles'] # Order from guide
    else:
        print("Invalid choice.")
        return
        
    for target in targets:
        print(f"\n--- Starting generation for {target} ---")
        run_generation(client, dataset, language, batch_size, workers, target)

def run_generation(client, dataset, language, batch_size, workers, target):
    procedure = f"BatchedUpdate{target}"
    
    jobs = []
    
    # If workers = 1, we don't need partitioning (PARTS=NULL, PART=NULL)
    if workers <= 1:
        sql = f"CALL `{client.project}.{dataset}`.{procedure}({batch_size}, '{language}', NULL, NULL, NULL);"
        print(f"Running: {sql}")
        try:
            job = client.query(sql)
            print(f"Job started. ID: {job.job_id}")
            jobs.append(job)
        except Exception as e:
            print(f"Error starting job: {e}")
            return
    else:
        print(f"Splitting work into {workers} parallel parts...")
        for part in range(workers):
            sql = f"CALL `{client.project}.{dataset}`.{procedure}({batch_size}, '{language}', {workers}, {part}, NULL);"
            print(f"Starting worker {part}/{workers}: {sql}")
            try:
                job = client.query(sql)
                print(f"Worker {part} started. ID: {job.job_id}")
                jobs.append(job)
            except Exception as e:
                print(f"Error starting worker {part}: {e}")
            
    from tqdm import tqdm
    
    # Get total rows
    total_query = f"SELECT COUNT(*) as total FROM `{client.project}.{dataset}.InputProcessing`"
    try:
        total_rows = list(client.query(total_query).result())[0].total
    except Exception as e:
        tqdm.write(f"Warning: Could not get total row count: {e}")
        total_rows = 100 # Fallback
        
    pbar = tqdm(total=total_rows, desc=f"Generating {target}")
    
    # Query for processed count
    if target == 'Titles':
        processed_query = f"SELECT COUNT(*) as processed FROM `{client.project}.{dataset}.Output` WHERE title IS NOT NULL"
    else:
        processed_query = f"SELECT COUNT(*) as processed FROM `{client.project}.{dataset}.Output` WHERE description IS NOT NULL"

    all_done = False
    while not all_done:
        all_done = True
        running_count = 0
        for i, job in enumerate(jobs):
            job.reload()
            if not job.done():
                all_done = False
                running_count += 1
            else:
                if job.error_result:
                    tqdm.write(f"Job {i} ({job.job_id}) failed: {job.error_result['message']}")
                    
        # Update progress bar
        try:
            processed_rows = list(client.query(processed_query).result())[0].processed
            pbar.n = processed_rows
            pbar.refresh()
        except Exception as e:
            pass
            
        if not all_done:
            time.sleep(5) # Shorter sleep for smoother updates
            
    pbar.close()
            
    print(f"Finished generation for {target}.")

if __name__ == "__main__":
    main()
