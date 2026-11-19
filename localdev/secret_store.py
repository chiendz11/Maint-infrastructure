"""Restore the owned LocalStack store from private local state, without argv secrets."""

import json
import subprocess

from .common import LOCAL, kube, read


def put_local_secrets(documents):
    program = """import sys,json,boto3
c=boto3.client('secretsmanager',endpoint_url='http://localhost:4566',region_name='ap-southeast-1',aws_access_key_id='test',aws_secret_access_key='test')
try:
 for name,value in json.load(sys.stdin).items():
  try:c.create_secret(Name=name,SecretString=json.dumps(value))
  except c.exceptions.ResourceExistsException:c.put_secret_value(SecretId=name,SecretString=json.dumps(value))
except Exception as e:
 print('Local secret-store write failed: '+type(e).__name__)
 sys.exit(1)
print('Local Secrets Manager values restored; no values printed.')
"""
    try:
        kube("exec", "-i", "deployment/localstack", "--", "python", "-c", program,
             namespace="localstack", stdin=json.dumps(documents), capture=True)
    except subprocess.CalledProcessError:
        raise RuntimeError("Local secret-store write failed; check LocalStack readiness") from None


def documents(credentials, groq_key):
    if not groq_key or "\n" in groq_key:
        raise ValueError("Provide a nonempty single-line private Groq key")
    pg = credentials["postgres"]

    def url(role, database, host):
        return f"postgresql://{role}:{pg[role + '_password']}@{host}/{database}_db"

    return {
        "maintai/local/database": {
            "BUSINESS_DATABASE_URL": url("business_api", "business", "postgres:5432"),
            "PROCESSING_DATABASE_URL": url("processing_worker", "processing", "postgres:5432"),
            "PROCESSING_READ_DATABASE_URL": url("processing_reader", "processing", "postgres:5432"),
            "KNOWLEDGE_DATABASE_URL": url("knowledge_owner", "knowledge", "postgres:5432"),
            "DRIFT_DATABASE_URL": url("drift_owner", "drift", "postgres:5432"),
        },
        "maintai/local/storage": {
            "AWS_ACCESS_KEY_ID": "maintai-storage",
            "AWS_SECRET_ACCESS_KEY": credentials["minio"]["storage_password"],
            "AWS_REGION": "us-east-1", "AWS_DEFAULT_REGION": "us-east-1",
        },
        "maintai/local/training": {
            "AWS_ACCESS_KEY_ID": "maintai-training",
            "AWS_SECRET_ACCESS_KEY": credentials["minio"]["training_password"],
            "AWS_REGION": "us-east-1", "AWS_DEFAULT_REGION": "us-east-1",
        },
        "maintai/local/inference": {
            "AWS_ACCESS_KEY_ID": "maintai-inference",
            "AWS_SECRET_ACCESS_KEY": credentials["minio"]["inference_password"],
            "AWS_REGION": "us-east-1", "AWS_DEFAULT_REGION": "us-east-1",
        },
        "maintai/local/llm": {"GROQ_API_KEY": groq_key},
    }


def gitops_document(username, pat):
    if not username or "\n" in username or not pat or "\n" in pat:
        raise ValueError("Provide nonempty single-line GitHub username and PAT")
    return {"maintai/local/gitops": {"username": username, "password": pat}}


def _read_private_file(path, message):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(message)
    return path.read_text(encoding="utf-8").strip()


def main():
    key = _read_private_file(LOCAL / "secrets/groq-api-key", "Groq key must be a private regular file (mode600)")
    entries = documents(read(LOCAL / "credentials.json"), key)
    pat_file = LOCAL / "secrets/image-updater-pat"
    if pat_file.exists() or pat_file.is_symlink():
        pat = _read_private_file(pat_file, "Image Updater PAT must be a private regular file (mode600)")
        user_file = LOCAL / "secrets/image-updater-username"
        username = _read_private_file(user_file, "Image Updater username must be a private regular file (mode600)")
        entries.update(gitops_document(username, pat))
    put_local_secrets(entries)
    print("Database/storage/Groq/GitOps entries restored in owned LocalStack; existing passwords preserved.")


if __name__ == "__main__":
    main()
