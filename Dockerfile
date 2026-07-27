FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DAGSTER_HOME=/app/dagster_home
RUN mkdir -p /app/dagster_home

RUN cd dbt && DBT_PROFILES_DIR=. dbt parse --target prod || \
    echo "dbt parse deferred to runtime (warehouse not reachable at build time)"

EXPOSE 3000
CMD ["dagster", "dev", "-h", "0.0.0.0", "-p", "3000", "-f", "orchestration/dagster_pipeline.py"]
