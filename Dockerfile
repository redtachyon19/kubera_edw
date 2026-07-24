# Image for the orchestrator (Dagster) — also usable to run ingestion / dbt one-offs.
FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2 / builds kept minimal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3000
CMD ["dagster", "dev", "-h", "0.0.0.0", "-p", "3000", "-f", "orchestration/dagster_pipeline.py"]
