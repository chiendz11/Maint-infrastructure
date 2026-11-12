"""Explicit local M6 credentials, verified delegation identity and owner grants."""

import argparse
import base64
import json
import secrets
import ssl
import sys
import urllib.parse
import urllib.request
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from .common import LOCAL, apply, checkout, kube, read, write_json
from .credentials import initialize
from .secret_store import put_local_secrets

ISSUER = "https://127.0.0.1:18490/realms/maintai"
HISTORY_ISSUER = "http://127.0.0.1:18091/maintai-history"


def service_subject(credentials):
    """Verify a fresh service token obtained over the owned issuer's TLS endpoint."""
    context = ssl.create_default_context(cafile=str(LOCAL / "tls/ca.crt"))
    payload = urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": "maintai-processing",
        "client_secret": credentials["oidc"]["processing_secret"],
    }).encode()
    request = urllib.request.Request(ISSUER + "/protocol/openid-connect/token", data=payload)
    with urllib.request.urlopen(request, context=context, timeout=10) as response:
        token = json.load(response)["access_token"]
    with urllib.request.urlopen(ISSUER + "/protocol/openid-connect/certs", context=context, timeout=10) as response:
        keys = json.load(response)["keys"]
    header = jwt.get_unverified_header(token)
    matches = [item for item in keys if item.get("kid") == header.get("kid")]
    if header.get("alg") != "RS256" or len(matches) != 1:
        raise ValueError("Unexpected service signing key")
    claims = jwt.decode(token, jwt.PyJWK.from_dict(matches[0]).key, algorithms=["RS256"],
                        issuer=ISSUER, audience="maintai-processing-local",
                        options={"require": ["sub", "iss", "aud", "exp"]})
    if "BUSINESS_SERVICE" not in claims.get("roles", []) or not claims.get("machine_ids"):
        raise ValueError("Processing service identity lacks its scoped role")
    return claims["sub"]


def new_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    kid = "history-" + uuid.uuid4().hex[:16]
    public = {name: value for name, value in jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True).items() if name in {"kty", "n", "e"}}
    public.update(kid=kid, alg="RS256", use="sig")
    return {"private_key": pem, "kid": kid, "jwks": {"keys": [public]},
            "business_cursor": base64.b64encode(secrets.token_bytes(32)).decode(),
            "processing_cursor": base64.b64encode(secrets.token_bytes(32)).decode()}


def cursor(value):
    if len(base64.b64decode(value, validate=True)) < 32:
        raise ValueError("Cursor keys must contain at least32 bytes")
    return json.dumps({"active": "v1", "keys": {"v1": value}})


def prepare():
    initialize()
    path = LOCAL / "secrets/history.json"
    if not path.exists():
        write_json(path, new_keys())
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("History state must be a private regular file")
    keys = read(path)
    signing = serialization.load_pem_private_key(keys["private_key"].encode(), password=None)
    if not isinstance(signing, rsa.RSAPrivateKey) or signing.key_size < 2048:
        raise ValueError("Invalid history RSA identity")
    expected = jwt.algorithms.RSAAlgorithm.to_jwk(signing.public_key(), as_dict=True)
    actual = keys["jwks"]["keys"][0]
    if any(actual.get(name) != expected[name] for name in ("kty", "n", "e")) or actual.get("kid") != keys["kid"]:
        raise ValueError("History public/private keys disagree")
    normalized = {name: actual[name] for name in ("kty", "n", "e", "kid", "alg", "use")}
    if actual != normalized:
        keys["jwks"] = {"keys": [normalized]}
        write_json(path, keys)
    if keys["business_cursor"] == keys["processing_cursor"]:
        raise ValueError("The two cursor credentials must be independent")
    cursor(keys["business_cursor"]); cursor(keys["processing_cursor"])
    subject = service_subject(read(LOCAL / "credentials.json"))
    target = checkout("gitops_checkout") / "config/local/history-runtime.json"
    previous = read(target) if target.exists() else {}
    document = {"schema_version": "1.0.0", "enabled": previous.get("enabled", False),
                "issuer": HISTORY_ISSUER, "service_subject": subject, "signing_key_id": keys["kid"],
                "jwks": keys["jwks"], "adapter_image": previous.get("adapter_image"),
                "raw_bucket": previous.get("raw_bucket", "maintai-raw")}
    for field in ("archive_group_prefix", "archive_lineage", "archive_replicas"):
        if field in previous: document[field] = previous[field]
    target.write_text(json.dumps(document, indent=2) + "\n")
    print("Private RSA/cursor keys preserved; public selector contains verified service subject.")


def seed():
    """Only this namespace's LocalStack receives the secret payload, via stdin."""
    keys = read(LOCAL / "secrets/history.json")
    credentials = read(LOCAL / "credentials.json")
    password = credentials["postgres"]["processing_history_meta_password"]
    documents = {
        "maintai/local/history-business": {"signing-key.pem": keys["private_key"], "cursor-keys.json": cursor(keys["business_cursor"])},
        "maintai/local/history-processing-keys": {"cursor-keys.json": cursor(keys["processing_cursor"])},
        "maintai/local/history-processing-env": {
            "PROCESSING_HISTORY_METADATA_DATABASE_URL": f"postgresql://processing_history_meta:{password}@postgres:5432/processing_db",
            "AWS_ACCESS_KEY_ID": "maintai-history", "AWS_SECRET_ACCESS_KEY": credentials["minio"]["history_password"],
            "AWS_REGION": "us-east-1", "AWS_DEFAULT_REGION": "us-east-1",
        },
    }
    put_local_secrets(documents)
    print("History secrets stored in local Secrets Manager; values not printed.")
    # These two bootstrap fields are not managed by ESO. Preserve all existing data.
    for name, field, value in (
        ("local-postgres-bootstrap", "processing_history_meta_password", password),
        ("local-minio-bootstrap", "history_password", credentials["minio"]["history_password"]),
    ):
        patch = {"data": {field: base64.b64encode(value.encode()).decode()}}
        kube("patch", "secret", name, "--type=merge", "--patch-file=/dev/stdin",
             stdin=json.dumps(patch), capture=True)


def provision():
    """Run only owner SQL; no outcome/source data mutation or credential logging."""
    pods = json.loads(kube("get", "pods", "-l", "app.kubernetes.io/name=processing-read-api", "-o", "json", capture=True))
    images = {c["imageID"].removeprefix("docker-pullable://") for p in pods["items"]
              for c in p.get("status", {}).get("containerStatuses", [])
              if c["name"] == "processing-read-api" and c.get("ready")}
    if len(images) != 1:
        raise ValueError("One reviewed running Read API image is required")
    image = images.pop()
    if "@sha256:" not in image:
        raise ValueError("Owner operation requires the resolved application image digest")
    program = """import os,psycopg
from psycopg import sql
from urllib.parse import urlparse
from processing.shared.history_meta.persistence import grant_metadata
u=urlparse(os.environ['METADATA_URL']);role='processing_history_meta'
if u.username!=role:raise ValueError('Wrong metadata identity')
with psycopg.connect(host='postgres',port=5432,dbname='processing_db',user='postgres',password=os.environ['ADMIN_PASSWORD']) as c:
 if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
  c.execute(sql.SQL('CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal(u.password)))
 c.execute(sql.SQL('GRANT CONNECT ON DATABASE processing_db TO {}').format(sql.Identifier(role)))
with psycopg.connect(os.environ['PROCESSING_OWNER']) as c:grant_metadata(c,role=role)
with psycopg.connect(os.environ['BUSINESS_OWNER']) as c:
 c.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON history_marker_snapshots TO business_api')
print('History metadata and marker grants completed; no source data changed.')
"""
    name = "local-history-grants-" + uuid.uuid4().hex[:12]
    env = []
    for variable, secret, key in (
        ("ADMIN_PASSWORD", "local-postgres-admin", "password"),
        ("METADATA_URL", "local-processing-history-env", "PROCESSING_HISTORY_METADATA_DATABASE_URL"),
        ("PROCESSING_OWNER", "local-processing-owner", "url"),
        ("BUSINESS_OWNER", "local-business-owner", "url"),
    ):
        env.append({"name": variable, "valueFrom": {"secretKeyRef": {"name": secret, "key": key}}})
    apply([{"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": name, "namespace": "maintai-local"},
            "spec": {"backoffLimit": 0, "activeDeadlineSeconds": 180, "ttlSecondsAfterFinished": 86400,
                     "template": {"spec": {"restartPolicy": "Never", "automountServiceAccountToken": False,
                        "containers": [{"name": "owner", "image": image, "command": ["python", "-c", program], "env": env}]}}}}])
    kube("wait", "--for=condition=complete", "job/" + name, "--timeout=180s")
    write_json(LOCAL / "history-owner-receipt.json", {"job": name, "image": image, "source_data_changed": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "seed", "provision", "build-adapter"])
    args = parser.parse_args()
    try:
        if args.operation == "prepare": prepare()
        elif args.operation == "seed": seed()
        elif args.operation == "provision": provision()
        else:
            from .cli import image_receipt
            from .common import ROOT
            image_receipt("dev-tools", ROOT, "local/runtime/Dockerfile", "local/runtime")
    except Exception:
        print("History operation failed; inspect private operator state. Credentials are not logged.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
