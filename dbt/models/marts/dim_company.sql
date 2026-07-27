
with snapshotted as (

    select * from {{ ref('company_snapshot') }}

),

ordered as (

    select
        *,
        row_number() over (
            partition by ticker
            order by dbt_valid_from
        ) as version_number

    from snapshotted

),

versioned as (

    select
        {{ dbt_utils.generate_surrogate_key(['ticker', 'dbt_valid_from']) }} as company_key,

        ticker,
        cik,
        legal_name,
        sector,
        industry,
        filer_type,
        country_iso3,
        currency_iso        as domestic_currency,
        reporting_currency,
        xbrl_taxonomy,
        fiscal_year_end,
        version_number,

        case
            when version_number = 1 then cast(valid_from as date)
            else cast(dbt_valid_from as date)
        end                                     as effective_from,

        cast(dbt_valid_to as date)              as effective_to,
        (dbt_valid_to is null)                  as is_current

    from ordered

)

select * from versioned
