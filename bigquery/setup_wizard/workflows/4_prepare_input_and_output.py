import argparse
import sys
from google.cloud import bigquery

DEFAULT_DATASET = "feedgen_dataset"
DEFAULT_SOURCE_TABLE = "InputFiltered"
DEFAULT_OUTPUT_TABLE = "Output"
DEFAULT_INPUT_PROCESSING_TABLE = "InputProcessing"
DEFAULT_WEB_TABLE = "InputFilteredWeb"
DEFAULT_IMAGES_TABLE = "InputFilteredImages"

def main():
    parser = argparse.ArgumentParser(description="Prepare InputProcessing and Output tables in BigQuery.")
    parser.add_argument("--dataset", default=DEFAULT_DATASET, help="BigQuery dataset name")
    parser.add_argument("--source_table", default=DEFAULT_SOURCE_TABLE, help="Source table name (e.g., InputFiltered)")
    parser.add_argument("--output_table", default=DEFAULT_OUTPUT_TABLE, help="Output table name")
    parser.add_argument("--input_processing_table", default=DEFAULT_INPUT_PROCESSING_TABLE, help="Input processing table name")
    parser.add_argument("--web_table", default=DEFAULT_WEB_TABLE, help="Web descriptions table name")
    parser.add_argument("--images_table", default=DEFAULT_IMAGES_TABLE, help="Image descriptions table name")
    
    args = parser.parse_args()
    
    try:
        client = bigquery.Client()
    except Exception as e:
        print(f"Error initializing BigQuery client: {e}")
        sys.exit(1)
        
    # 1. Prepare InputProcessing
    input_proc_id = f"{client.project}.{args.dataset}.{args.input_processing_table}"
    source_id = f"{client.project}.{args.dataset}.{args.source_table}"
    web_id = f"{client.project}.{args.dataset}.{args.web_table}"
    images_id = f"{client.project}.{args.dataset}.{args.images_table}"
    
    # Example query from guide, using content from web and description from images
    sql_input = f"""
    CREATE OR REPLACE TABLE `{input_proc_id}` AS
    SELECT
      F.id, F.title, F.description,
      W.content AS webpage_content,
      I.description AS image_description
    FROM `{source_id}` AS F
    LEFT JOIN `{web_id}` AS W USING (id)
    LEFT JOIN `{images_id}` AS I
      ON F.image_link LIKE CONCAT('%', REGEXP_EXTRACT(uri, '.*/([^/]+)'), '%');
    """
    
    print(f"Creating/Replacing table {input_proc_id}...")
    try:
        job = client.query(sql_input)
        job.result()
        print(f"Table {input_proc_id} created successfully.")
    except Exception as e:
        print(f"Error creating InputProcessing table: {e}")
        print("You may need to adjust the query or ensure source tables exist.")
        print("Check if column names like 'image_link' match your source table.")
        
    # 2. Prepare Output
    output_id = f"{client.project}.{args.dataset}.{args.output_table}"
    
    sql_output = f"""
    CREATE OR REPLACE TABLE `{output_id}` AS
    SELECT
      id,
      CAST(NULL AS STRING) AS title,
      CAST(NULL AS STRING) AS description,
      0 AS tries,
      CAST(NULL AS TIMESTAMP) AS updated_at
    FROM `{source_id}`;
    """
    
    print(f"Creating/Replacing table {output_id} using source {source_id}...")
    try:
        job = client.query(sql_output)
        job.result()
        print(f"Table {output_id} initialized successfully.")
    except Exception as e:
        print(f"Error initializing Output table: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
