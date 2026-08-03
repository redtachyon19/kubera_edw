
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

    (extract(dow from full_date) not in (0, 6))                   as is_weekday,

    (extract(month from full_date)
        <> extract(month from full_date + interval '1 day'))      as is_month_end,

    (extract(month from full_date) in (3, 6, 9, 12)
        and extract(month from full_date)
            <> extract(month from full_date + interval '1 day'))  as is_quarter_end,

    (extract(month from full_date) in (3, 6, 9, 12)
        and extract(month from full_date)
            <> extract(month from full_date + interval '1 day'))  as is_period_end

from calendar
