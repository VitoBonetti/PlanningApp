from google.cloud import bigquery
from datetime import datetime, timezone
import os

# Define your GCP Project and Dataset
PROJECT_ID = "planningapp-491007"
DATASET_ID = "erp_audit_logs"
TABLE_ID = "system_events"
LOCATION = "europe-west4"


def get_bq_client():
    # Only try to connect if we are in production (or if you have local ADC set up)
    if os.environ.get("ENV") == "local":
        return None
    try:
        return bigquery.Client(project=PROJECT_ID)
    except Exception as e:
        print(f"Failed to initialize BigQuery Client: {e}")
        return None


def init_audit_log_infrastructure():
    """
    Runs on startup: Creates the BigQuery Dataset and Table (with schema) if they don't exist.
    """
    client = get_bq_client()
    if not client:
        print("Running locally: Skipping BigQuery Infrastructure Setup.")
        return

    # 1. Create Dataset if not exists
    dataset_ref = f"{PROJECT_ID}.{DATASET_ID}"
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = LOCATION
    try:
        dataset = client.create_dataset(dataset, exists_ok=True)
        print(f"BigQuery Dataset '{DATASET_ID}' verified/created.")
    except Exception as e:
        print(f"Failed to create dataset: {e}")

    # 2. Define the Schema
    schema = [
        bigquery.SchemaField("timestamp", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("username", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("action", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("resource_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("resource_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("details", "STRING", mode="NULLABLE"),
    ]

    # 3. Create Table if not exists
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
    table = bigquery.Table(table_ref, schema=schema)

    # ENTERPRISE FEATURE: Partition the table by Day to save money on future queries!
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="timestamp",
    )

    try:
        client.create_table(table, exists_ok=True)
        print(f"BigQuery Table '{TABLE_ID}' verified/created.")
    except Exception as e:
        print(f"Failed to create table: {e}")


def log_audit_event(user_id: str, username: str, action: str, resource_type: str, resource_id: str = None,
                    details: str = None):
    """Streams an audit event to BigQuery."""
    client = get_bq_client()
    if not client:
        print(f"[LOCAL AUDIT LOG] {username} performed {action} on {resource_type}: {details}")
        return

    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    row_to_insert = [{
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": str(user_id),
        "username": str(username),
        "action": str(action),
        "resource_type": str(resource_type),
        "resource_id": str(resource_id) if resource_id else None,
        "details": str(details) if details else None
    }]

    try:
        errors = client.insert_rows_json(table_ref, row_to_insert)
        if errors:
            print(f"BigQuery Insert Errors: {errors}")
    except Exception as e:
        print(f"Failed to log to BigQuery: {e}")