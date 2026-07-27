"""KPI queries against the marts, mapped to the framework in docs/project_spec.md §10.

Every query reads marts only — never staging, never raw. If a KPI needs logic beyond a
select, that logic belongs in dbt where it is tested, not in the dashboard.
"""

from __future__ import annotations

import pandas as pd

from .db import query


# --------------------------------------------------------------- portfolio allocation
def holdings() -> pd.DataFrame:
    """Current company versions with their classification attributes."""
    return query(
        """
        select ticker, legal_name, sector, country_iso3, domestic_currency,
               reporting_currency, filer_type, xbrl_taxonomy
        from marts.dim_company
        where is_current
        order by ticker
        """
    )


def allocation(dimension: str) -> pd.DataFrame:
    """Equal-weighted allocation by a classification dimension.

    EQUAL WEIGHT IS AN EXPLICIT ASSUMPTION, not a measurement. Kubera's positions are a
    simulation (§13) and the warehouse holds no share counts, so there are no real weights to
    compute — and market-cap weighting is unavailable while prices are missing. Presenting
    equal weight labelled as such is honest; inventing weights would not be.
    """
    column = {
        "Country": "c.country_name",
        "Sector": "d.sector",
        "Currency": "d.domestic_currency",
        "Region": "c.region",
    }[dimension]
    return query(
        f"""
        select {column} as category,
               count(*) as holdings,
               100.0 * count(*) / sum(count(*)) over () as weight_pct
        from marts.dim_company d
        left join marts.dim_country c on c.iso3_code = d.country_iso3
        where d.is_current
        group by 1
        order by holdings desc, category
        """
    )


# --------------------------------------------------------------- fundamentals
def fundamentals(period_type: str = "FY") -> pd.DataFrame:
    """Annual (or quarterly) fundamentals in USD with margins and growth."""
    return query(
        f"""
        with base as (
            select ticker, fiscal_year, period_end_date, reporting_currency,
                   revenue, revenue_usd, net_income_usd, ebitda_usd,
                   ebitda_margin, net_margin, gross_margin,
                   net_debt_usd, net_debt_to_ebitda, cash_and_equivalents
            from marts.fact_financials
            where period_type = '{period_type}'
        )
        select *,
               revenue_usd / nullif(lag(revenue_usd) over (
                   partition by ticker order by fiscal_year), 0) - 1 as revenue_growth_yoy,
               net_income_usd / nullif(lag(net_income_usd) over (
                   partition by ticker order by fiscal_year), 0) - 1 as net_income_growth_yoy
        from base
        order by ticker, fiscal_year
        """
    )


# --------------------------------------------------------------- FX impact
def fx_impact() -> pd.DataFrame:
    """Companies whose financials genuinely require currency conversion.

    Only TM (JPY) and BABA (CNY) report in a non-USD currency; AZN, SHEL and INFY are foreign
    issuers that file with the SEC in USD, so for them conversion is a deliberate no-op.
    """
    return query(
        """
        select ticker, fiscal_year, reporting_currency, rate_per_usd,
               fx_rate_carried_forward, revenue, revenue_usd, ebitda_usd
        from marts.fact_financials
        where period_type = 'FY'
          and reporting_currency <> 'USD'
          and revenue is not null
        order by ticker, fiscal_year
        """
    )


def fx_rate_history() -> pd.DataFrame:
    """Year-end conversion rates actually applied to the financials."""
    return query(
        """
        select ticker, reporting_currency, fiscal_year, rate_per_usd
        from marts.fact_financials
        where period_type = 'FY' and reporting_currency <> 'USD' and rate_per_usd is not null
        order by fiscal_year
        """
    )


# --------------------------------------------------------------- macro overlay
def macro() -> pd.DataFrame:
    """Country-year macro, with the IMF cross-check carried alongside World Bank."""
    return query(
        """
        select country_iso3, region, calendar_year,
               gdp, gdp_growth_pct, cpi_inflation_pct, unemployment_pct,
               fx_rate_to_usd, imf_gdp_growth_pct, gdp_growth_source_diff
        from marts.fact_macro_indicators
        where calendar_year is not null
        order by country_iso3, calendar_year
        """
    )


# --------------------------------------------------------------- market performance
def market_prices() -> pd.DataFrame:
    """Daily USD prices and returns from Alpha Vantage (free tier: latest ~100 days)."""
    return query(
        """
        select ticker, trade_date, close_price_usd, daily_return, volume
        from marts.fact_market_prices
        order by ticker, trade_date
        """
    )


def gold_prices() -> pd.DataFrame:
    """Daily gold benchmark (currently the GLD ETF proxy — see gold_price_client)."""
    return query(
        """
        select price_date, series_id, source, gold_price_usd, daily_change_pct
        from marts.fact_gold_price
        order by price_date
        """
    )
