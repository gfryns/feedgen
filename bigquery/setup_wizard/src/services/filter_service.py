from services.bq_client import get_bq_client

def create_filtered_table(project_val: str, dataset_val: str, raw_table: str, id_col: str, title_col: str, desc_col: str, url_col: str, image_col: str, include_cols: str, filters: str, insecure: bool, log_cb=print):
    """Creates the InputFiltered table in BigQuery based on user options."""
    log_cb("Creating filtered table...\n")
    
    if include_cols.strip() == '*':
        cols_str = '*'
    else:
        cols = [f"{id_col} as id", f"{title_col} as title", f"{desc_col} as description"]
        if url_col != 'skip':
            cols.append(f"{url_col} as url")
        if image_col != 'skip':
            cols.append(f"{image_col} as image_url")
            
        for c in include_cols.split(','):
            c = c.strip()
            if c and c not in [id_col, title_col, desc_col, url_col, image_col]:
                cols.append(c)
                
        cols_str = ", ".join(cols)
        
    if '.' in raw_table:
        parts = raw_table.split('.')
        raw_table_ref = ".".join([f"`{p}`" for p in parts])
    else:
        raw_table_ref = f"`{project_val}.{dataset_val}.{raw_table}`"
        
    sql_filter = f"""
    CREATE OR REPLACE TABLE `{project_val}.{dataset_val}.InputFiltered` AS
    SELECT {cols_str}
    FROM {raw_table_ref}
    {filters}
    """
    
    log_cb(f"Executing SQL:\n{sql_filter}\n")
    
    client = get_bq_client(project_val, insecure)
    client.query(sql_filter).result()
    log_cb("Table created successfully!\n")
