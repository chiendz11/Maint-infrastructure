"""Local credentials/TLS generation; idempotent unless an operator rotates them."""

import base64
import json
import os
import secrets
from pathlib import Path

from .common import CONTRACT, LOCAL, NAMESPACE, ROOT, apply, read, run, write_json

OWNERS = ("processing", "business", "drift", "knowledge", "mlflow")
ROLES = tuple(name + "_owner" for name in OWNERS) + (
    "processing_worker", "processing_relay", "processing_reader", "business_api", "business_consumer", "business_reader"
)


def initialize():
    LOCAL.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(LOCAL, 0o700)
    for area in ("state", "data/datasets", "data/models", "data/fixtures", "receipts", "tls", "secrets"):
        (LOCAL / area).mkdir(parents=True, exist_ok=True, mode=0o700)
    for area in ("data", "data/datasets", "data/models", "data/fixtures"):
        os.chmod(LOCAL / area, 0o755)
    os.chmod(LOCAL / "secrets", 0o700)
    if not (LOCAL / "settings.json").exists():
        write_json(LOCAL / "settings.json", read(ROOT / "local/config/settings.example.json"))
    if not (LOCAL / "credentials.json").exists():
        users = read(ROOT / "local/config/buckets.json")["users"]
        value = {"postgres": {role + "_password": secrets.token_hex(24) for role in ROLES},
                 "postgres_admin_password": secrets.token_hex(24),
                 "minio": {name + "_password": secrets.token_hex(24) for name in users},
                 "minio_root_password": secrets.token_hex(24), "keycloak_admin_password": secrets.token_hex(24),
                 "grafana_password": secrets.token_hex(24),
                 "oidc": {name + "_secret": secrets.token_hex(32) for name in ("registry", "processing", "sensor", "ml")},
                 "users": {name: secrets.token_hex(16) for name in ("viewer", "technician", "administrator")},
                 "kafka_cluster_id": base64.urlsafe_b64encode(secrets.token_bytes(16)).decode().rstrip("=")}
        write_json(LOCAL / "credentials.json", value)


def certificates():
    folder = LOCAL / "tls"
    if (folder / "tls.crt").exists():
        if not all((folder / name).is_file() for name in ("tls.key", "ca.crt", "ca.key")):
            raise ValueError("Partial TLS state; restore the original local CA before continuing")
        return
    run(["openssl", "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-days", "365",
         "-keyout", str(folder / "ca.key"), "-out", str(folder / "ca.crt"),
         "-subj", "/CN=MaintAI Local Development CA", "-addext", "basicConstraints=critical,CA:TRUE"], capture=True)
    run(["openssl", "req", "-newkey", "rsa:3072", "-nodes", "-keyout", str(folder / "tls.key"),
         "-out", str(folder / "tls.csr"), "-subj", "/CN=localhost"], capture=True)
    extension = folder / "leaf.ext"
    extension.write_text("subjectAltName=DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\n")
    run(["openssl", "x509", "-req", "-in", str(folder / "tls.csr"), "-CA", str(folder / "ca.crt"),
         "-CAkey", str(folder / "ca.key"), "-CAcreateserial", "-out", str(folder / "tls.crt"),
         "-days", "90", "-extfile", str(extension)], capture=True)
    for name in ("ca.key", "tls.key"):
        os.chmod(folder / name, 0o600)


def resource(name, values):
    return {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": NAMESPACE,
            "labels": {"maintai.io/owner": "local-bootstrap"}}, "type": "Opaque", "stringData": values}


def secret_resources():
    value = read(LOCAL / "credentials.json")
    pg, s3 = value["postgres"], value["minio"]

    def dsn(role, owner, loopback=True, driver="postgresql"):
        address = "127.0.0.1:25432" if loopback else "postgres:5432"
        return f"{driver}://{role}:{pg[role + '_password']}@{address}/{owner}_db"

    def aws(name):
        return {"AWS_ACCESS_KEY_ID": "maintai-" + name, "AWS_SECRET_ACCESS_KEY": s3[name + "_password"], "AWS_REGION": "us-east-1", "AWS_DEFAULT_REGION": "us-east-1"}

    docs = [resource("local-postgres-admin", {"password": value["postgres_admin_password"]}),
            resource("local-postgres-bootstrap", {"admin_password": value["postgres_admin_password"], **pg}),
            resource("local-kafka", {"cluster_id": value["kafka_cluster_id"]}),
            resource("local-minio-admin", {"access_key": "maintai-root", "secret_key": value["minio_root_password"]}),
            resource("local-minio-bootstrap", {"root_access_key": "maintai-root", "root_secret_key": value["minio_root_password"], **s3}),
            resource("local-keycloak-admin", {"username": "admin", "password": value["keycloak_admin_password"]}),
            resource("local-idp-users", value["users"]), resource("local-grafana", {"admin-password": value["grafana_password"]}),
            resource("local-dev-tls", {name: (LOCAL / "tls" / name).read_text() for name in ("tls.crt", "tls.key", "ca.crt")})]
    for owner in OWNERS:
        docs.append(resource("local-" + owner + "-owner", {"url": dsn(owner + "_owner", owner, False)}))
    for runtime, role, owner, variable in (
        ("processing-worker", "processing_worker", "processing", "PROCESSING_DATABASE_URL"),
        ("processing-outbox-relay", "processing_relay", "processing", "PROCESSING_DATABASE_URL"),
        ("processing-read-api", "processing_reader", "processing", "PROCESSING_READ_DATABASE_URL"),
        ("business-api", "business_api", "business", "BUSINESS_DATABASE_URL"),
        ("business-consumer", "business_consumer", "business", "BUSINESS_DATABASE_URL"),
    ):
        docs.append(resource("local-" + runtime + "-env", {variable: dsn(role, owner)}))
    for runtime, identity in (("storage", "storage"), ("ml-service", "inference"), ("training", "training")):
        docs.append(resource("local-" + runtime + "-env", aws(identity)))
    docs += [resource("local-rag-service-env", {"DATABASE_URL": dsn("knowledge_owner", "knowledge", False), **aws("rag")}),
             resource("local-drift-worker-env", {"DRIFT_DATABASE_URL": dsn("drift_owner", "drift", False), **aws("drift")}),
             resource("local-mlflow-env", {"MLFLOW_BACKEND_STORE_URI": dsn("mlflow_owner", "mlflow", False, "postgresql+psycopg2"), "MLFLOW_S3_ENDPOINT_URL": "http://minio:9000", **aws("mlflow")})]
    for name in ("registry", "processing", "sensor", "ml"):
        docs.append(resource("local-oidc-" + name, {"client_id": "maintai-" + name, "client_secret": value["oidc"][name + "_secret"]}))
    return docs


def install_secrets():
    certificates()
    apply([{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NAMESPACE}}])
    apply(secret_resources())
    install_groq_secret(required=False)
    print("Local secrets installed through stdin. No secret values were printed or committed.")


def groq_secret_resource(required=True):
    """Read only the operator's private file, never an environment/chat fallback."""
    path = LOCAL / "secrets/groq-api-key"
    if not path.exists():
        if required:
            raise ValueError("Store a new Groq key in private local/.local/secrets/groq-api-key first")
        return None
    if path.is_symlink() or not path.resolve().is_relative_to(LOCAL.resolve()) or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("Groq key must be a private regular file (chmod 600)")
    with path.open() as stream:
        value = stream.read(16385).strip()
    if not value.startswith("gsk_") or len(value) > 16384 or any(char.isspace() for char in value):
        raise ValueError("Groq credential file is invalid")
    return resource("rag-groq", {"GROQ_API_KEY": value})


def install_groq_secret(required=True):
    document = groq_secret_resource(required=required)
    if document is not None:
        apply([document])
        print("Scoped rag-groq Secret installed; restart RAG after credential rotation.")
