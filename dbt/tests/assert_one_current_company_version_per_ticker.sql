
select
    ticker,
    count(*) as current_versions

from {{ ref('dim_company') }}
where is_current

group by ticker
having count(*) > 1
