-- The thirteen goods categories the trade desk colours by.
--
-- This is the join that lets the global layer and the US layer share one legend.
-- PortWatch names its industries directly and tags each with the HS sections it
-- spans; Census reports HS chapters. `seed_hs_industry.csv` maps all 97 chapters
-- onto the same thirteen names, so a ribbon coloured "Metals" from PortWatch and
-- a US customs row coloured "Metals" from chapter 72 are the same colour and
-- mean the same thing.
--
-- `industry_order` fixes the palette assignment. Ordering these by size or by
-- name would move a category's colour whenever the data shifted, and a legend
-- that changes colour between two page loads is worse than no legend.

with mapping as (

    select * from {{ ref('seed_hs_industry') }}

),

industries as (

    select
        industry            as industry_name,
        hs_section,
        industry_order,
        count(*)            as hs_chapter_count,
        min(hs_chapter)     as first_hs_chapter,
        max(hs_chapter)     as last_hs_chapter
    from mapping
    group by industry, hs_section, industry_order

)

select
    {{ dbt_utils.generate_surrogate_key(['industry_name']) }}   as industry_key,
    industry_name,
    hs_section,
    industry_order,
    hs_chapter_count,
    first_hs_chapter,
    last_hs_chapter
from industries
