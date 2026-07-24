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

# Persist run history, schedules and sensor state across container restarts. Without
# DAGSTER_HOME, Dagster falls back to a temp directory and loses everything on restart.
ENV DAGSTER_HOME=/app/dagster_home
RUN mkdir -p /app/dagster_home

# Bake the dbt manifest into the image. @dbt_assets needs manifest.json at import time to build
# the asset graph; generating it at container start would make the code location fail to load
# on a cold boot before any dbt command has ever run.
RUN cd dbt && DBT_PROFILES_DIR=. dbt parse --target prod || \
    echo "dbt parse deferred to runtime (warehouse not reachable at build time)"

EXPOSE 3000
CMD ["dagster", "dev", "-h", "0.0.0.0", "-p", "3000", "-f", "orchestration/dagster_pipeline.py"]
