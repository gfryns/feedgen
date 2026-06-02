from services.bq_client import get_bq_client
from google.cloud import storage
import gspread
import csv
import io
import google.auth

def get_table_columns(project: str, dataset: str, table_name: str) -> list:
    """Fetches column names for a given BigQuery table."""
    client = get_bq_client(project)
    if '.' in table_name:
        parts = table_name.split('.')
        table_ref = ".".join([f"`{p}`" for p in parts])
    else:
        table_ref = f"`{project}.{dataset}.{table_name}`"
        
    # Remove backticks for get_table
    table_id = table_ref.replace("`", "")
    table = client.get_table(table_id)
    return [field.name for field in table.schema]

def export_to_gmc(project_val: str, dataset_val: str, raw_table: str, output_table: str, export_table: str, feed_type: str, destination_type: str = "gcs", destination_target: str = "", filename: str = "supplemental_feed.csv", sheet_name: str = "Sheet1", log_cb=print, export_title: bool = True, export_desc: bool = True, export_highlights: bool = True):
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
    
    # Resolve raw table ref (Source Table)
    if '.' in raw_table:
        parts = raw_table.split('.')
        raw_table_ref = ".".join([f"`{p}`" for p in parts])
    else:
        raw_table_ref = f"`{project_val}.{dataset_val}.{raw_table}`"
        
    if feed_type == "supplemental":
        log_cb("Creating Supplemental Feed view...\n")
        
        cols = ["id"]
        if export_title:
            cols.append(f"`{project_val}.{dataset_val}.EmbedForMerchantFeed`(title, TRUE) AS structured_title")
        if export_desc:
            cols.append(f"`{project_val}.{dataset_val}.EmbedForMerchantFeed`(description, TRUE) AS structured_description")
        if export_highlights:
            cols.append(f"          CONCAT('trained_algorithmic_media:', highlights) AS product_highlight")
            
        cols_str = ", ".join(cols)
        
        where_clauses = []
        if export_title: where_clauses.append("title IS NOT NULL")
        if export_desc: where_clauses.append("description IS NOT NULL")
        if export_highlights: where_clauses.append("highlights IS NOT NULL")
        
        where_str = " OR ".join(where_clauses) if where_clauses else "TRUE"
        
        sql = f"""
        SELECT
          {cols_str}
        FROM {raw_table_ref}
        WHERE {where_str};
        """
    elif feed_type == "full":
        log_cb("Creating Full Feed view...\n")
            
        except_cols = []
        if export_title: except_cols.append("title")
        if export_desc: except_cols.append("description")
        
        if except_cols:
            select_cols = [f"I.* EXCEPT ({', '.join(except_cols)})"]
        else:
            select_cols = ["I.*"]
            
        if export_title:
            select_cols.append(f"`{project_val}.{dataset_val}.EmbedForMerchantFeed`(COALESCE(O.title, I.title), O.title IS NOT NULL) AS structured_title")
        if export_desc:
            select_cols.append(f"`{project_val}.{dataset_val}.EmbedForMerchantFeed`(COALESCE(O.description, I.description), O.description IS NOT NULL) AS structured_description")
        if export_highlights:
            select_cols.append(f"IF(O.highlights IS NOT NULL, CONCAT('trained_algorithmic_media:', O.highlights), I.product_highlight) AS product_highlight")
            
        select_str = ", ".join(select_cols)
        
        sql = f"""
        SELECT
          {select_str}
        FROM {raw_table_ref} AS I
        LEFT JOIN {output_ref} AS O USING (id);
        """
    else:
        raise ValueError(f"Unknown feed type: {feed_type}")
        
    log_cb(f"Executing SQL to fetch data...\n")
    rows = client.query(sql).result()
    schema = rows.schema
    rows_list = list(rows)
    log_cb(f"Fetched {len(rows_list)} rows from BigQuery.\n")
    
    # 3. Export to destination
    if destination_type == "gcs":
        if not destination_target:
            log_cb("Error: GCS bucket name not provided.\n")
            return
        log_cb(f"Exporting data to GCS bucket: {destination_target} as {filename}...\n")
        

        
        # Convert to CSV
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        
        # Write header
        writer.writerow([field.name for field in schema])
        
        # Write rows
        for row in rows_list:
            writer.writerow(list(row.values()))
            
        # Upload to GCS
        storage_client = storage.Client(project=project_val)
        bucket = storage_client.bucket(destination_target)
        blob = bucket.blob(filename)
        blob.upload_from_string(csv_buffer.getvalue(), content_type='text/csv')
        log_cb(f"Successfully uploaded to gs://{destination_target}/{filename}\n")
        
    elif destination_type == "sheets":
        if not destination_target:
            log_cb("Error: Google Sheet ID not provided.\n")
            return
        log_cb(f"Exporting data to Google Sheet: {destination_target}...\n")
        

        
        # Convert to list of lists
        data = [[field.name for field in schema]]
        for row in rows_list:
            data.append(list(row.values()))
            
        # Authenticate and connect to sheet
        try:
            gc = gspread.oauth()
        except Exception:
            credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/spreadsheets'])
            gc = gspread.Client(auth=credentials)
            
        sh = gc.open_by_key(destination_target)
        
        worksheet_names = [w.title for w in sh.worksheets()]
        if sheet_name in worksheet_names:
            worksheet = sh.worksheet(sheet_name)
        else:
            log_cb(f"Worksheet '{sheet_name}' not found. Creating it...\n")
            worksheet = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
        
        # Clear and update
        worksheet.clear()
        worksheet.update('A1', data)
        log_cb(f"Successfully exported to Google Sheet '{sheet_name}'.\n")
        
    else:
        log_cb(f"Skipping file export (Unknown destination type: {destination_type}).\n")
