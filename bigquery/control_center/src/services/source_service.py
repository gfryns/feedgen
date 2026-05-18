import re
from services.bq_client import get_bq_client

def get_table_info(project_val: str, dataset_val: str, raw_table: str, target_region: str, log_cb=print):
    """Fetches schema and a preview of the source BigQuery table."""
    if '.' not in raw_table:
        full_ref = f"{project_val}.{dataset_val}.{raw_table}"
    else:
        full_ref = raw_table
        
    client = get_bq_client(project_val)
    table = client.get_table(full_ref)
    location = table.location
    num_rows = table.num_rows
    cols = [field.name for field in table.schema]
    
    warnings = []
    if location.upper() != target_region.upper():
        warnings.append(f"Warning: Table is in {location}, but dataset is in {target_region}!")
        
    short_cols = cols[:5]
    cols_str = ", ".join(short_cols)
    if len(cols) > 5:
        cols_str += ", ..."
        
    summary = f"Table found! - {full_ref} ({location}): {num_rows} rows, {len(cols)} columns ({cols_str})"
    
    if not cols:
        return {
            'summary': summary,
            'warnings': warnings,
            'cols': [],
            'preview': []
        }
    
    id_col = next((c for c in cols if re.search(r'(id|sku)', c, re.I)), cols[0])
    title_col = next((c for c in cols if re.search(r'(title|name)', c, re.I)), cols[1] if len(cols)>1 else cols[0])
    desc_col = next((c for c in cols if re.search(r'(desc|text|summary)', c, re.I)), cols[2] if len(cols)>2 else cols[0])
    
    query = f"SELECT {id_col}, {title_col}, {desc_col} FROM `{full_ref}` LIMIT 5"
    res = list(client.query(query).result())
    
    # Convert RowIterator results to list of dicts for the UI
    preview_data = [
        (str(row[id_col]), str(row[title_col]), str(row[desc_col])) 
        for row in res
    ]
    
    return {
        'summary': summary,
        'warnings': warnings,
        'cols': cols,
        'preview': preview_data
    }
