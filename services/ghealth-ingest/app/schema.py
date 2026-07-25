"""Verified mappings for the initial ghealth data set.

These keys match `ghealth --raw` output.  The ingest worker refuses an
unexpected envelope and always retains the complete point in JSONB.
"""

INITIAL_TYPES = {
    "heart-rate": "list",
    "steps": "daily-rollup",
    "sleep": "list",
    "exercise": "list",
    "weight": "list",
}

REQUIRED_OPERATIONS = {
    "heart-rate": {"list"},
    "steps": {"daily-rollup"},
    "sleep": {"list"},
    "exercise": {"list"},
    "weight": {"list"},
}


def expected_rows_key(operation: str) -> str:
    if operation == "list":
        return "dataPoints"
    if operation == "daily-rollup":
        return "rollupDataPoints"
    raise ValueError(f"Unsupported ghealth operation: {operation}")
