import logging
import json

# Mapping of error codes to error types
ERROR_TYPE_MAP = {
    "101": "empty_file"
    # "102": "invalid_format",
    # Add more codes and their types as needed
}

def log_error(file_name: str, code: str):
    error_type = ERROR_TYPE_MAP.get(code, "unknown_error")

    log_entry = {
        "level": "error",
        "type": error_type,
        "code": code,
        "file": file_name
    }

    logging.error(json.dumps(log_entry))