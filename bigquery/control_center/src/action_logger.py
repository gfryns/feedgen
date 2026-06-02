import datetime
import os

DEBUG_LOG_FILE = "debug_action_log.txt"

def log_action(action: str, details: str = ""):
    """Writes an action to the debug log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_line = f"[{timestamp}] ACTION: {action}"
    if details:
        log_line += f" | DETAILS: {details}"
    log_line += "\n"
    
    with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line)
