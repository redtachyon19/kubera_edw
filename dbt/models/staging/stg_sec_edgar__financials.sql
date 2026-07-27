
with source as (

    select * from {{ source('raw', 'sec_edgar_facts') }}

),

renamed as (

    select
        cik,
        ticker,
        entity_name,
        taxonomy,
        concept,
        unit,
        cast(period_start as date)                  as period_start_date,
        cast(period_end   as date)                  as period_end_date,
        cast(value as {{ type_money() }})       as value_reported,
        cast(fiscal_year as {{ dbt.type_int() }})   as fiscal_year,
        fiscal_period,
        form,
        cast(filed_date as date)                    as filed_date,
        frame,
        accession

    from source
    where period_end is not null

)

select * from renamed
