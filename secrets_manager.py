import os
import json
from google.cloud import secretmanager
from google.api_core.exceptions import NotFound


PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
if not PROJECT_ID and os.environ.get("ENV") != "local":
    raise EnvironmentError("GCP_PROJECT_ID environment variable is not set.")

SECRET_ID = os.environ.get("SECRET_ID")
if not SECRET_ID and os.environ.get("ENV") != "local":
    raise EnvironmentError("SECRET_ID environment variable is not set.")

LOCAL_MOCK_FILE = ".mock_secrets.json"

def get_system_config():
    """
    Attempts to fetch the system configuration from GCP Secret Manager.
    Returns the JSON dict if found.
    Returns None if it doesn't exist (Triggering Day 0 Setup).
    """
    if os.environ.get("ENV") == "local":
        print("[LOCAL MODE] Bypassing GCP Secret Manager.")
        # Try to read the local mock file if it exists
        if os.path.exists(LOCAL_MOCK_FILE):
            with open(LOCAL_MOCK_FILE, "r") as f:
                return json.load(f)
        # Return None here if you want to test the Day 0 Wizard locally!
        return None

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/{SECRET_ID}/versions/latest"

    try:
        response = client.access_secret_version(request={"name": name})
        secret_string = response.payload.data.decode("UTF-8")
        return json.loads(secret_string)
    except NotFound:
        print(f"🚨 Day 0 State Detected: {SECRET_ID} secret not found in GCP.")
        return None
    except Exception as e:
        print(f"Error accessing Secret Manager: {e}")
        return None

def save_system_config(payload: dict):
    """
    Takes the Day 0 Setup Wizard payload and locks it into GCP Secret Manager.
    Creates the secret container if it doesn't exist, then adds the version.
    """
    if os.environ.get("ENV") == "local":
        print("[LOCAL MODE] Saving to local mock file.")
        # Save the config locally so we don't have to setup again
        with open(LOCAL_MOCK_FILE, "w") as f:
            json.dump(payload, f, indent=2)
        return True

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{PROJECT_ID}"
    secret_name = f"{parent}/secrets/{SECRET_ID}"

    # 1. Check if the secret container exists; if not, create it
    try:
        client.get_secret(request={"name": secret_name})
    except NotFound:
        print(f"Creating new Secret Manager container: {SECRET_ID}")
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": SECRET_ID,
                "secret": {"replication": {"automatic": {}}},
            }
        )

    # 2. Add the actual payload as a new version
    payload_bytes = json.dumps(payload).encode("UTF-8")
    client.add_secret_version(
        request={
            "parent": secret_name,
            "payload": {"data": payload_bytes},
        }
    )
    print("✅ System configuration securely locked in GCP Secret Manager.")
    return True