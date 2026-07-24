{#
    Use custom schema names verbatim instead of dbt's default "<target_schema>_<custom>".

    Two reasons:

    1. The `raw` schema must be spelled exactly `raw`, because two different producers write it:
       the Python loader (`ingestion/load_raw.py`) in dev/prod, and committed CI fixture seeds in
       CI. Both have to land where `{{ source('raw', ...) }}` looks, or the DAG silently splits
       into two incompatible worlds.

    2. It yields the schema names an analyst actually expects — staging / intermediate / marts /
       snapshots — rather than main_staging / main_marts.

    Models with no custom schema still fall back to the target schema.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}

{%- endmacro %}
