# Build from the repository root:  docker build -f api/Dockerfile .
# The image holds the API, the seed config and the course folders. It runs as an unprivileged user.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 ISD_VAR_DIR=/tmp/isd
WORKDIR /app
# Dependencies first, so a code change does not reinstall them.
# Behind a proxy that inspects TLS, build with ISD_EXTRA_CA=/path/to/ca.pem (docs/demo-guide.md).
COPY deploy/build-ca /tmp/build-ca
COPY api/pyproject.toml ./
RUN if [ -f /tmp/build-ca/extra-ca.pem ]; then export PIP_CERT=/tmp/build-ca/extra-ca.pem; fi; \
    mkdir isd && pip install -e . && rm -rf isd
COPY api/ ./
COPY config /config
COPY content /content
COPY scripts /scripts
RUN if [ -f /tmp/build-ca/extra-ca.pem ]; then export PIP_CERT=/tmp/build-ca/extra-ca.pem; fi; \
    pip install -e . --no-deps \
 && useradd --system --uid 10001 --home-dir /nonexistent isd \
 && mkdir -p /tmp/isd && chown isd /tmp/isd
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "isd.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
