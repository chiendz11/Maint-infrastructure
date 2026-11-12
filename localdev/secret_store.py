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
        "maintai/local/llm": {"GROQ_API_KEY": groq_key},
    }


def main():
    key_file = LOCAL / "secrets/groq-api-key"
    if key_file.is_symlink() or not key_file.is_file() or key_file.stat().st_mode & 0o077:
        raise ValueError("Groq key must be a private regular file (mode600)")
    put_local_secrets(documents(read(LOCAL / "credentials.json"), key_file.read_text().strip()))
    print("Database/storage/Groq entries restored in owned LocalStack; existing passwords preserved.")


if __name__ == "__main__":
    main()
