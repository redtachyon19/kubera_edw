"""Kubera_EDW ingestion layer.

One client per external data source. Each client extracts raw responses and lands them
as-is under ``data/raw/<source>/`` (no transformation — that happens in dbt staging).
"""
