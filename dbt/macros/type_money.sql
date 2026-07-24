{#
    Numeric type for monetary amounts, rates and indicator values.

    NOT dbt.type_float(): that resolves to FLOAT (32-bit) on DuckDB, which carries only ~7
    significant decimal digits. Financial statement values run to 14 digits — Toyota reports
    revenue of 48,036,704,000,000 JPY — so a 32-bit float silently rounds it to
    48,036,705,206,272 and INVENTS 1.2 million yen that no filing ever reported.

    `double precision` is 64-bit (~15-17 significant digits) and represents every integer below
    2^53 exactly, which covers every value this warehouse holds. It is also spelled identically
    in DuckDB and Postgres, so the models stay portable across both targets.
#}
{% macro type_money() %}double precision{% endmacro %}
