import json, os, boto3
from pathlib import Path
from urllib import request, error

ALB_BASE_URL = os.environ["ALB_BASE_URL"]
DOCS_API_PATH = os.environ.get("DOCS_API_PATH", "/api/documents")
TOKEN_SECRET_ARN = os.environ["INGESTION_API_TOKEN_ARN"]

secrets_client = boto3.client("secretsmanager")

def get_ingestion_token():
    return secrets_client.get_secret_value(SecretId=TOKEN_SECRET_ARN)["SecretString"]

def get_key_and_event_type(overrides):
    if not overrides:
        return None, None

    env_list = overrides[0].get("environment", [])
    env_map = {item.get("name"): item.get("value") for item in env_list}

    return env_map.get("S3_OBJECT_KEY"), env_map.get("EVENT_TYPE")

def status_from_event_type(event_type):
    if event_type == "Object Created":
        return "failed"
    if event_type == "Object Deleted":
        return "delete_failed"
    return None

def patch_status(document_id, status, token):
    url = f"{ALB_BASE_URL}{DOCS_API_PATH}/{document_id}"
    body = json.dumps({"status": status}).encode("utf-8")

    req = request.Request(url, data=body, method="PATCH")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-api-token", token)

    print(f"[PATCH] {url} → {status}")

    try:
        resp = request.urlopen(req, timeout=30)
        resp_body = resp.read().decode("utf-8", "replace")
        print("Response:", resp.getcode(), resp_body)
    except error.HTTPError as e:
        err_body = e.read().decode("utf-8", "replace")
        print("HTTPError:", e.code, err_body)
        raise
    except error.URLError as e:
        print("URLError:", e)
        raise


def handle_run_task_dlq(payload, token):
    key, event_type = get_key_and_event_type(payload.get("containerOverrides", []))

    if not key or not event_type:
        print("[WARN] Missing S3_OBJECT_KEY or EVENT_TYPE in RunTask payload; skipping")
        return

    status = status_from_event_type(event_type)
    if not status:
        print("[WARN] Unknown EVENT_TYPE in RunTask payload:", event_type)
        return

    document_id = Path(key).stem
    patch_status(document_id, status, token)

def handle_ecs_task_failure(payload, token):
    detail = payload.get("detail", {})
    overrides = detail.get("overrides", {}).get("containerOverrides", [])

    key, event_type = get_key_and_event_type(overrides)

    if not key or not event_type:
        print("[WARN] Missing S3_OBJECT_KEY or EVENT_TYPE in ECS detail; skipping")
        return

    status = status_from_event_type(event_type)
    if not status:
        print("[WARN] Unknown EVENT_TYPE in ECS detail:", event_type)
        return

    document_id = Path(key).stem
    patch_status(document_id, status, token)


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

        detail_type = payload.get("detail-type")

        # 1) Failed ingestion tasks (STOPPED + non-zero exitCode) from ECS rule
        if detail_type == "ECS Task State Change":
            handle_ecs_task_failure(payload, token)
            continue

        # 2) Failed RunTask invocations from EventBridge DLQ
        if "containerOverrides" in payload:
            handle_run_task_dlq(payload, token)
            continue

        print("[WARN] Unrecognized payload shape; keys:", list(payload.keys()))
