# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 APP_DATA_DIR=/data
WORKDIR /app
COPY requirements.lock.txt ./
RUN --mount=type=secret,id=cloud_ca \
    if [ -f /run/secrets/cloud_ca ]; then export PIP_CERT=/run/secrets/cloud_ca; fi; \
    pip install --no-cache-dir --require-hashes -r requirements.lock.txt && \
    useradd --uid 10001 --create-home app && mkdir -p /data /app/data && chown app:app /data /app/data
COPY --chown=app:app app ./app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
