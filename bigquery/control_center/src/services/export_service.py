from services.bq_client import get_bq_client

def export_to_gmc(project_val: str, dataset_val: str, raw_table: str, output_table: str, export_table: str, feed_type: str, log_cb=print):
    """Creates the EmbedForMerchantFeed UDF and exports the generated data."""
    log_cb("Starting Merchant Center Export process...\n")
    client = get_bq_client(project_val)
    
    # 1. Create the formatting function
    log_cb("Deploying EmbedForMerchantFeed function...\n")
    udf_sql = f"""
    CREATE OR REPLACE FUNCTION `{project_val}.{dataset_val}.EmbedForMerchantFeed`(value STRING, isAiGenerated BOOL) AS (
      CONCAT(IF(isAiGenerated, 'trained_algorithmic_media', ''), ':"', REPLACE(value, '"', '""'), '"')
    );
    """
    client.query(udf_sql).result()
    log_cb("Function EmbedForMerchantFeed deployed.\n")
    
    # 2. Construct the export query based on feed type
    output_ref = f"`{project_val}.{dataset_val}.{output_table}`"
    export_ref = f"`{project_val}.{dataset_val}.{export_table}`"
    
    if feed_type == "supplemental":
        log_cb("Creating Supplemental Feed view...\n")
        sql = f"""
        CREATE OR REPLACE TABLE {export_ref} AS
        SELECT
          id,
          `{project_val}.{dataset_val}.EmbedForMerchantFeed`(title, TRUE) AS structured_title,
          `{project_val}.{dataset_val}.EmbedForMerchantFeed`(description, TRUE) AS structured_description
        FROM {output_ref}
        WHERE title IS NOT NULL OR description IS NOT NULL;
        """
    elif feed_type == "full":
        log_cb("Creating Full Feed view...\n")
        # Resolve raw table ref
        if '.' in raw_table:
            parts = raw_table.split('.')
            raw_table_ref = ".".join([f"`{p}`" for p in parts])
        else:
            raw_table_ref = f"`{project_val}.{dataset_val}.{raw_table}`"
            
        sql = f"""
        CREATE OR REPLACE TABLE {export_ref} AS
        SELECT
          I.* EXCEPT (title, description),
          `{project_val}.{dataset_val}.EmbedForMerchantFeed`(COALESCE(O.title, I.title), O.title IS NOT NULL) AS structured_title,
          `{project_val}.{dataset_val}.EmbedForMerchantFeed`(COALESCE(O.description, I.description), O.description IS NOT NULL) AS structured_description
        FROM {raw_table_ref} AS I
        LEFT JOIN {output_ref} AS O USING (id);
        """
    else:
        raise ValueError(f"Unknown feed type: {feed_type}")
        
    log_cb(f"Executing SQL:\n{sql}\n")
    client.query(sql).result()
    log_cb(f"Export table {export_ref} created successfully!\n")
