FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY legacy/railway/requirements-cloud.txt .
RUN pip install --no-cache-dir -r requirements-cloud.txt

COPY app ./app

CMD ["sh", "-c", "uvicorn app.cloud_main:app --host 0.0.0.0 --port ${PORT:-8000}"]
