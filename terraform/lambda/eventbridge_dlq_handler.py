import json, os, boto3
from pathlib import Path
from urllib import request, error

ALB_BASE_URL = os.environ["ALB_BASE_URL"]
DOCS_API_PATH = os.environ.get("DOCS_API_PATH", "/api/documents")
TOKEN_SECRET_ARN = os.environ["INGESTION_API_TOKEN_ARN"]

secrets_client = boto3.client("secretsmanager")

def get_ingestion_token():
    resp = secrets_client.get_secret_value(SecretId=TOKEN_SECRET_ARN)
    return resp["SecretString"]

def handler(event, context):
    records = event.get("Records", [])
    if not records:
        return

    token = get_ingestion_token()

    for record in records:
        body = record.get("body", "")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            print("[WARN] Bad JSON body:", body[:200])
            continue

        overrides = payload.get("containerOverrides", [])
        if not overrides:
            print("[WARN] No containerOverrides in payload")
            continue

        env_list = overrides[0].get("environment", [])
        env_map = {item["name"]: item["value"] for item in env_list}

        bucket = env_map.get("S3_BUCKET_NAME")
        key = env_map.get("S3_OBJECT_KEY")
        event_type = env_map.get("EVENT_TYPE")

        if not key or not event_type:
            print("[WARN] Missing S3_OBJECT_KEY or EVENT_TYPE; skipping")
            continue

        document_id = Path(key).stem

        if event_type == "Object Created":
            new_status = "failed"
        elif event_type == "Object Deleted":
            new_status = "delete_failed"
        else:
            print("[WARN] Unknown EVENT_TYPE:", event_type)
            continue

        url = f"{ALB_BASE_URL}{DOCS_API_PATH}/{document_id}"
        data = json.dumps({"status": new_status}).encode("utf-8")

        req = request.Request(url, data=data, method="PATCH")
        req.add_header("Content-Type", "application/json")
        req.add_header("x-api-token", token)

        print(f"[PATCH] {url} → {new_status}")

        try:
            resp = request.urlopen(req, timeout=60)
            status = resp.getcode()
            resp_body = resp.read().decode("utf-8", "replace")
            print("Response:", status, resp_body)

        except error.HTTPError as e:
            err_body = e.read().decode("utf-8", "replace")
            print("HTTPError:", e.code, err_body)
            raise
