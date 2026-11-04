#!/usr/bin/env python3
"""Seed local secrets into LocalStack Secrets Manager for MaintAI Phase 2."""

import json
import os
import subprocess
from pathlib import Path

KUBECONFIG = Path("/home/chienqt/Dev/newBTL/Maint-infrastructure/local/.local/kubeconfig")
CREDS_FILE = Path("/home/chienqt/Dev/newBTL/Maint-infrastructure/local/.local/credentials.json")
GROQ_FILE = Path("/home/chienqt/Dev/newBTL/Maint-infrastructure/local/.local/secrets/groq-api-key")

def run_kubectl_exec(cmd):
    full_cmd = [
        "kubectl", "--kubeconfig", str(KUBECONFIG), "-n", "localstack",
        "exec", "deploy/localstack", "--"
    ] + cmd
    return subprocess.run(full_cmd, capture_output=True, text=True, check=False)

def put_secret(name, data_dict):
    secret_str = json.dumps(data_dict)
    # Check if secret exists
    check = run_kubectl_exec(["awslocal", "secretsmanager", "describe-secret", "--secret-id", name])
    if check.returncode == 0:
        res = run_kubectl_exec(["awslocal", "secretsmanager", "put-secret-value", "--secret-id", name, "--secret-string", secret_str])
        print(f"Updated secret {name}: returncode {res.returncode}")
    else:
        res = run_kubectl_exec(["awslocal", "secretsmanager", "create-secret", "--name", name, "--secret-string", secret_str])
        print(f"Created secret {name}: returncode {res.returncode}")
    if res.returncode != 0:
        print(f"  Error: {res.stderr}")

def main():
    if not CREDS_FILE.exists():
        print(f"Credentials file {CREDS_FILE} not found!")
        return

    creds = json.loads(CREDS_FILE.read_text())
    pg = creds.get("postgres", {})
    s3 = creds.get("minio", {})

    db_secrets = {
        "BUSINESS_DATABASE_URL": f"postgresql://business_api:{pg.get('business_api_password', 'secret')}@postgres:5432/business_db",
        "PROCESSING_DATABASE_URL": f"postgresql://processing_worker:{pg.get('processing_worker_password', 'secret')}@postgres:5432/processing_db",
        "PROCESSING_READ_DATABASE_URL": f"postgresql://processing_reader:{pg.get('processing_reader_password', 'secret')}@postgres:5432/processing_db",
        "KNOWLEDGE_DATABASE_URL": f"postgresql://knowledge_owner:{pg.get('knowledge_owner_password', 'secret')}@postgres:5432/knowledge_db",
        "DRIFT_DATABASE_URL": f"postgresql://drift_owner:{pg.get('drift_owner_password', 'secret')}@postgres:5432/drift_db",
    }
    put_secret("maintai/local/database", db_secrets)

    groq_key = "gsk_local_mock_token_12345"
    if GROQ_FILE.exists():
        groq_key = GROQ_FILE.read_text().strip()
    put_secret("maintai/local/llm", {"GROQ_API_KEY": groq_key})

    storage_secrets = {
        "AWS_ACCESS_KEY_ID": "maintai-storage",
        "AWS_SECRET_ACCESS_KEY": s3.get("storage_password", "secret"),
        "AWS_REGION": "us-east-1",
        "AWS_DEFAULT_REGION": "us-east-1",
    }
    put_secret("maintai/local/storage", storage_secrets)

    auth_secrets = {
        "JWT_SECRET": "maintai-local-super-secret-jwt-key",
        "processing_client_secret": creds.get("oidc", {}).get("processing_secret", "secret"),
        "sensor_client_secret": creds.get("oidc", {}).get("sensor_secret", "secret"),
    }
    put_secret("maintai/local/auth", auth_secrets)

    print("All secrets seeded into LocalStack Secrets Manager successfully.")

if __name__ == "__main__":
    main()
