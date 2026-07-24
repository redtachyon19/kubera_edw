-- dim_date — one row per calendar date. The conformed dimension every fact joins on.
--
-- CALENDAR attributes only, deliberately. The portfolio spans five different fiscal calendars
-- (Apple ends Sep, Microsoft Jun, Toyota/Infosys/Alibaba Mar, the rest Dec), so a single
-- "fiscal_quarter" column here would be wrong for at least four companies. Company-specific
-- fiscal periods travel on the FACT instead, from SEC's own fy/fp fields — which is also the
-- only way to honour the mixed quarterly (10-Q) vs annual-only (20-F) cadence (§11).
--
-- Range covers the earliest landed filing period (AstraZeneca, 2003) through 2030.

with spine as (

    {{ dbt_utils.date_spine(
        datepart="day",
        start_date="cast('" ~ var('date_spine_start') ~ "' as date)",
        end_date="cast('" ~ var('date_spine_end') ~ "' as date)"
    ) }}

),

calendar as (

    select
        cast(date_day as date) as full_date
    from spine

)

select
    -- Integer YYYYMMDD key, built arithmetically so it is portable across DuckDB/Postgres
    -- (strftime and to_char are dialect-specific).
    cast(
        extract(year  from full_date) * 10000
      + extract(month from full_date) * 100
      + extract(day   from full_date)
    as {{ dbt.type_int() }})                                    as date_key,

    full_date,
    cast(extract(year    from full_date) as {{ dbt.type_int() }}) as calendar_year,
    cast(extract(quarter from full_date) as {{ dbt.type_int() }}) as calendar_quarter,
    cast(extract(month   from full_date) as {{ dbt.type_int() }}) as calendar_month,
    cast(extract(day     from full_date) as {{ dbt.type_int() }}) as day_of_month,
    cast(extract(dow     from full_date) as {{ dbt.type_int() }}) as day_of_week,

    -- Weekend flag approximates non-trading days; real market holidays are not modelled.
    (extract(dow from full_date) not in (0, 6))                   as is_weekday,

    -- True on the last day of the calendar month — the usual filing/period boundary.
    (extract(month from full_date)
        <> extract(month from full_date + interval '1 day'))      as is_month_end,

    (extract(month from full_date) in (3, 6, 9, 12)
        and extract(month from full_date)
            <> extract(month from full_date + interval '1 day'))  as is_quarter_end,

    -- is_period_end (project_spec.md §9): true only on calendar quarter-end dates
    -- (Mar 31 / Jun 30 / Sep 30 / Dec 31) — the reporting-period boundaries facts land on.
    (extract(month from full_date) in (3, 6, 9, 12)
        and extract(month from full_date)
            <> extract(month from full_date + interval '1 day'))  as is_period_end

from calendar
