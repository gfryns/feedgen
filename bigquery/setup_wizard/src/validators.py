import re

def is_valid_project_id(project_id: str) -> bool:
    """
    Validates a Google Cloud Project ID.
    Rules: 6 to 30 lowercase letters, digits, or hyphens.
    Must start with a letter. Cannot end with a hyphen.
    """
    if not project_id:
        return False
    # Google Cloud Project ID regex
    pattern = r'^[a-z][a-z0-9-]{4,28}[a-z0-9]$'
    return bool(re.match(pattern, project_id))

def is_valid_dataset_name(dataset_name: str) -> bool:
    """
    Validates a BigQuery Dataset name.
    Rules: Up to 1024 characters.
    Letters, numbers, and underscores only.
    """
    if not dataset_name:
        return False
    # BigQuery Dataset name regex
    pattern = r'^[a-zA-Z0-9_]{1,1024}$'
    return bool(re.match(pattern, dataset_name))
