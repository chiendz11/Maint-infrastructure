# Development adapter only; no model, app code or production credentials.
FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /tools
COPY *.py /tools/
USER 10001:10001
ENTRYPOINT ["python", "/tools/main.py"]
