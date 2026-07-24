# Architecture Diagram

_Placeholder._ Replace this file with `architecture_diagram.png` in Phase 9 (Polish).

Suggested tool: draw.io / Excalidraw / Mermaid export. The diagram should show the flow:

`Public APIs → ingestion clients → data/raw → dbt (staging → intermediate → marts) →
warehouse (DuckDB/Postgres) → Dagster orchestration → Metabase/Streamlit BI`.
