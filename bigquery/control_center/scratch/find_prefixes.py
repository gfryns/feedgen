from google.cloud import storage
import sys
import os

def main():
    project = "test-gfryns"
    bucket_name = "test-gfryns-feedgen-us"
    
    print(f"Listing blobs in gs://{bucket_name}/output/")
    client = storage.Client(project=project)
    bucket = client.get_bucket(bucket_name)
    
    for target in ["titles", "descriptions"]:
        print(f"\nFolders in output_{target}:")
        prefix = f"output/output_{target}/"
        blobs = list(bucket.list_blobs(prefix=prefix))
        
        prefixes = set()
        for b in blobs:
            parts = b.name.split('/')
            if len(parts) > 2:
                prefixes.add('/'.join(parts[:3]) + '/')
                
        for p in sorted(list(prefixes)):
            print(p)

if __name__ == "__main__":
    main()
