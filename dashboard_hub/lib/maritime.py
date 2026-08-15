"""The trade desk: ports, chokepoints, and the flows between them.

Everything here reads the warehouse. That is the point of it — `lib/trade.py`
fetches WITS on demand and caches to disk, which is fine for a figure that
changes once a year, and useless for a series. These marts are built by dbt from
seven and a half years of daily IMF PortWatch history, so a port's page can show
what actually happened to it rather than one number with no context.

The two modules are kept apart because they answer different questions and the
answers do not overlap:

* `trade.py` — country ↔ country, in dollars, annually, from customs
  declarations. Who trades with whom.
* here — port-level tonnage daily, chokepoint transits daily, and port ↔ country
  flows valued by industry. Where it physically goes and what it is.

**Nothing in this module falls back to a live API.** If the warehouse is not
built, these return empty and the desk says so. That is deliberate: quietly
serving a different, thinner dataset under the same shape is how a panel ends up
lying about its own provenance.

Attribution: IMF PortWatch. Bulk redistribution is not granted, which is why the
figures are served from our own warehouse rather than proxied.
"""

from __future__ import annotations

from typing import Any

from dashboard_hub.lib.market_data import _cached
from dashboard_hub.lib.warehouse import _postgres, _rows

# The marts rebuild weekly at most, so these can be held for a long time. The
# cost of a miss is a real query against 5.7M rows.
_TTL = 1800

# How many ribbons the globe gets by default. Beyond a few hundred the picture
# stops being a map of trade and becomes a ball of wool — and the payload starts
# to matter over the wire.
_RIBBON_LIMIT = 320

# Ports drawn on the overview. All 2,065 is too many dots to distinguish and
# most of the tail moves almost nothing.
_PORT_LIMIT = 420


def _marker(index: int = 0) -> str:
    """The bind-parameter spelling for whichever engine is behind the warehouse."""
    return f":{index}" if _postgres() else "?"


def _num(value: Any) -> float | None:
    """Postgres hands back Decimal for numerics; JSON does not know what that is."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and out not in (float("inf"), float("-inf")) else None


def _date(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (value or None)


def available() -> bool:
    """True when the trade marts exist and can be read."""
    return bool(_rows("select 1 as ok from marts.dim_port limit 1"))


# ── The globe ────────────────────────────────────────────────────────────────


def _ports(limit: int) -> list[dict]:
    rows = _rows(
        f"""
        select port_id, port_name, country_iso3, country_name,
               latitude, longitude,
               recent_tons, prior_tons, tons_change,
               recent_port_calls, recent_import_tons, recent_export_tons,
               recent_tons_container, recent_tons_dry_bulk, recent_tons_tanker,
               industry_top1, tonnage_rank, last_activity_date
        from marts.dim_port
        where recent_tons > 0
        order by recent_tons desc
        limit {_marker(0)}
        """,
        [limit],
    )
    return [
        {
            "portId": row["port_id"],
            "name": row["port_name"],
            "iso3": row["country_iso3"],
            "country": row["country_name"],
            "lat": _num(row["latitude"]),
            "lon": _num(row["longitude"]),
            "tons": _num(row["recent_tons"]),
            "priorTons": _num(row["prior_tons"]),
            "change": _num(row["tons_change"]),
            "portCalls": _num(row["recent_port_calls"]),
            "importTons": _num(row["recent_import_tons"]),
            "exportTons": _num(row["recent_export_tons"]),
            "containerTons": _num(row["recent_tons_container"]),
            "dryBulkTons": _num(row["recent_tons_dry_bulk"]),
            "tankerTons": _num(row["recent_tons_tanker"]),
            "topIndustry": row["industry_top1"],
            "rank": row["tonnage_rank"],
            "asOf": _date(row["last_activity_date"]),
        }
        for row in rows
    ]


def _ribbons(limit: int) -> list[dict]:
    """The largest flows worldwide, both directions.

    `is_industry_dominant` decides whether the ribbon gets a goods colour at
    all. A link whose biggest industry is a third of it is genuinely that kind
    of route; one where it is 12% is a mixed container service, and painting it
    with the nominal winner would be inventing a fact.
    """
    rows = _rows(
        f"""
        select port_id, port_name, port_country_iso3, port_country_name,
               port_latitude, port_longitude,
               partner_country_iso3, partner_country_name,
               partner_latitude, partner_longitude,
               flow_direction, value_usd_daily, value_usd_annual,
               top_industry, top_industry_share, is_industry_dominant,
               industry_count, value_rank
        from marts.fact_trade_ribbon
        order by value_usd_daily desc
        limit {_marker(0)}
        """,
        [limit],
    )
    return [
        {
            "id": f"{row['port_id']}:{row['partner_country_iso3']}:{row['flow_direction']}",
            "portId": row["port_id"],
            "portName": row["port_name"],
            "portIso3": row["port_country_iso3"],
            "portCountry": row["port_country_name"],
            "fromLat": _num(row["port_latitude"]),
            "fromLon": _num(row["port_longitude"]),
            "partnerIso3": row["partner_country_iso3"],
            "partnerName": row["partner_country_name"],
            "toLat": _num(row["partner_latitude"]),
            "toLon": _num(row["partner_longitude"]),
            "direction": row["flow_direction"],
            "valueDaily": _num(row["value_usd_daily"]),
            "valueAnnual": _num(row["value_usd_annual"]),
            "industry": row["top_industry"] if row["is_industry_dominant"] else None,
            "industryShare": _num(row["top_industry_share"]),
            "industryCount": row["industry_count"],
            "rank": row["value_rank"],
        }
        for row in rows
    ]


def _chokepoints() -> list[dict]:
    rows = _rows(
        """
        select chokepoint_id, chokepoint_name, country_iso3, latitude, longitude,
               recent_transits, prior_transits, year_ago_transits,
               recent_capacity_dwt, prior_capacity_dwt, year_ago_capacity_dwt,
               transits_change, capacity_change, capacity_change_year_on_year,
               recent_transits_container, recent_transits_tanker,
               recent_transits_dry_bulk, last_transit_date
        from marts.dim_chokepoint
        order by recent_capacity_dwt desc
        """
    )
    return [
        {
            "chokepointId": row["chokepoint_id"],
            "name": row["chokepoint_name"],
            "iso3": row["country_iso3"],
            "lat": _num(row["latitude"]),
            "lon": _num(row["longitude"]),
            "transits": _num(row["recent_transits"]),
            "priorTransits": _num(row["prior_transits"]),
            "yearAgoTransits": _num(row["year_ago_transits"]),
            "capacity": _num(row["recent_capacity_dwt"]),
            "priorCapacity": _num(row["prior_capacity_dwt"]),
            "yearAgoCapacity": _num(row["year_ago_capacity_dwt"]),
            "transitsChange": _num(row["transits_change"]),
            "capacityChange": _num(row["capacity_change"]),
            "capacityChangeYoY": _num(row["capacity_change_year_on_year"]),
            "containerTransits": _num(row["recent_transits_container"]),
            "tankerTransits": _num(row["recent_transits_tanker"]),
            "dryBulkTransits": _num(row["recent_transits_dry_bulk"]),
            "asOf": _date(row["last_transit_date"]),
        }
        for row in rows
    ]


def industries() -> list[dict]:
    """The thirteen goods categories, in their fixed palette order."""
    rows = _rows(
        """
        select industry_name, hs_section, industry_order
        from marts.dim_industry
        order by industry_order
        """
    )
    return [
        {
            "name": row["industry_name"],
            "hsSection": row["hs_section"],
            "order": row["industry_order"],
        }
        for row in rows
    ]


def _overview(ports: int, ribbons: int) -> dict:
    rows = _rows(
        """
        select max(activity_date) as latest, min(activity_date) as earliest,
               count(*) as observations
        from marts.fact_port_activity_daily
        """
    )
    coverage = rows[0] if rows else {}

    return {
        "ports": _ports(ports),
        "ribbons": _ribbons(ribbons),
        "chokepoints": _chokepoints(),
        "industries": industries(),
        "coverage": {
            "from": _date(coverage.get("earliest")),
            "to": _date(coverage.get("latest")),
            "observations": coverage.get("observations"),
        },
        # Said plainly so the UI never has to imply this is live telemetry.
        "source": "IMF PortWatch · AIS-derived, republished weekly on Tuesdays",
    }


def overview(ports: int = _PORT_LIMIT, ribbons: int = _RIBBON_LIMIT) -> dict:
    return _cached(
        ("maritime", "overview", ports, ribbons),
        lambda: _overview(ports, ribbons),
        ttl=_TTL,
    )


# ── Detail: a port ───────────────────────────────────────────────────────────


def _port(port_id: str, weeks: int) -> dict:
    profile = _rows(
        f"""
        select port_id, port_name, port_full_name, locode, country_iso3, country_name,
               continent, latitude, longitude,
               industry_top1, industry_top2, industry_top3,
               share_country_maritime_import, share_country_maritime_export,
               recent_tons, prior_tons, tons_change, recent_port_calls,
               recent_import_tons, recent_export_tons,
               tonnage_rank, tonnage_rank_in_country, last_activity_date, is_catalogued
        from marts.dim_port
        where port_id = {_marker(0)}
        """,
        [port_id],
    )
    if not profile:
        return {"portId": port_id, "found": False}

    row = profile[0]

    history = _rows(
        f"""
        select week_start, total_tons, import_tons, export_tons, port_calls,
               import_tons_container + export_tons_container as container_tons,
               import_tons_dry_bulk  + export_tons_dry_bulk  as dry_bulk_tons,
               import_tons_tanker    + export_tons_tanker    as tanker_tons,
               total_tons_13w_avg, total_tons_year_ago,
               share_of_country_tons, is_complete_week
        from marts.fact_port_activity_weekly
        where port_id = {_marker(0)}
        order by week_start desc
        limit {_marker(1)}
        """,
        [port_id, weeks],
    )

    # The largest flows through this port, which is what makes the ribbons
    # legible one port at a time rather than as a global tangle.
    links = _rows(
        f"""
        select partner_country_iso3, partner_country_name, flow_direction,
               value_usd_daily, value_usd_annual, top_industry,
               top_industry_share, is_industry_dominant
        from marts.fact_trade_ribbon
        where port_id = {_marker(0)}
        order by value_usd_daily desc
        limit 24
        """,
        [port_id],
    )

    disruptions = _rows(
        f"""
        select event_id, event_type_name, event_name, alert_level, severity_text,
               started_on, ended_on, duration_days, affected_port_count
        from marts.fact_port_disruption
        where port_id = {_marker(0)}
        order by started_on desc
        limit 20
        """,
        [port_id],
    )

    return {
        "portId": row["port_id"],
        "found": True,
        "name": row["port_name"],
        "fullName": row["port_full_name"],
        "locode": row["locode"],
        "iso3": row["country_iso3"],
        "country": row["country_name"],
        "continent": row["continent"],
        "lat": _num(row["latitude"]),
        "lon": _num(row["longitude"]),
        "isCatalogued": row["is_catalogued"],
        "industries": [
            value
            for value in (row["industry_top1"], row["industry_top2"], row["industry_top3"])
            if value
        ],
        "shareOfCountryImports": _num(row["share_country_maritime_import"]),
        "shareOfCountryExports": _num(row["share_country_maritime_export"]),
        "tons": _num(row["recent_tons"]),
        "priorTons": _num(row["prior_tons"]),
        "change": _num(row["tons_change"]),
        "portCalls": _num(row["recent_port_calls"]),
        "importTons": _num(row["recent_import_tons"]),
        "exportTons": _num(row["recent_export_tons"]),
        "rank": row["tonnage_rank"],
        "rankInCountry": row["tonnage_rank_in_country"],
        "asOf": _date(row["last_activity_date"]),
        # Oldest first, which is the direction a chart draws.
        "history": [
            {
                "week": _date(h["week_start"]),
                "tons": _num(h["total_tons"]),
                "importTons": _num(h["import_tons"]),
                "exportTons": _num(h["export_tons"]),
                "portCalls": _num(h["port_calls"]),
                "containerTons": _num(h["container_tons"]),
                "dryBulkTons": _num(h["dry_bulk_tons"]),
                "tankerTons": _num(h["tanker_tons"]),
                "trend": _num(h["total_tons_13w_avg"]),
                "yearAgo": _num(h["total_tons_year_ago"]),
                "shareOfCountry": _num(h["share_of_country_tons"]),
                "partial": not h["is_complete_week"],
            }
            for h in reversed(history)
        ],
        "links": [
            {
                "partnerIso3": link["partner_country_iso3"],
                "partnerName": link["partner_country_name"],
                "direction": link["flow_direction"],
                "valueDaily": _num(link["value_usd_daily"]),
                "valueAnnual": _num(link["value_usd_annual"]),
                "industry": link["top_industry"] if link["is_industry_dominant"] else None,
                "industryShare": _num(link["top_industry_share"]),
            }
            for link in links
        ],
        "disruptions": [
            {
                "eventId": d["event_id"],
                "type": d["event_type_name"],
                "name": d["event_name"],
                "alertLevel": d["alert_level"],
                "severity": d["severity_text"],
                "from": _date(d["started_on"]),
                "to": _date(d["ended_on"]),
                "days": d["duration_days"],
                "portsHit": d["affected_port_count"],
            }
            for d in disruptions
        ],
    }


def port(port_id: str, weeks: int = 260) -> dict:
    """One port: profile, five years of weekly tonnage, its flows and its outages."""
    port_id = (port_id or "").strip()
    if not port_id:
        return {"portId": port_id, "found": False}
    return _cached(("maritime", "port", port_id, weeks), lambda: _port(port_id, weeks), ttl=_TTL)


# ── Detail: a ribbon ─────────────────────────────────────────────────────────


def _ribbon(port_id: str, partner_iso3: str, direction: str) -> dict:
    head = _rows(
        f"""
        select port_id, port_name, port_country_iso3, port_country_name,
               port_latitude, port_longitude,
               partner_country_iso3, partner_country_name,
               partner_latitude, partner_longitude,
               flow_direction, value_usd_daily, value_usd_annual,
               total_usd_daily, industry_sum_usd_daily,
               top_industry, top_industry_share, is_industry_dominant,
               industry_count, value_rank, value_rank_in_port, value_rank_in_country
        from marts.fact_trade_ribbon
        where port_id = {_marker(0)}
          and partner_country_iso3 = {_marker(1)}
          and flow_direction = {_marker(2)}
        """,
        [port_id, partner_iso3, direction],
    )
    if not head:
        return {"found": False}

    row = head[0]

    breakdown = _rows(
        f"""
        select industry_name, hs_section, industry_order,
               value_usd_daily, value_usd_annual, share_of_link, industry_rank
        from marts.fact_trade_ribbon_industry
        where port_id = {_marker(0)}
          and partner_country_iso3 = {_marker(1)}
          and flow_direction = {_marker(2)}
        order by value_usd_daily desc
        """,
        [port_id, partner_iso3, direction],
    )

    return {
        "found": True,
        "id": f"{port_id}:{partner_iso3}:{direction}",
        "portId": row["port_id"],
        "portName": row["port_name"],
        "portIso3": row["port_country_iso3"],
        "portCountry": row["port_country_name"],
        "fromLat": _num(row["port_latitude"]),
        "fromLon": _num(row["port_longitude"]),
        "partnerIso3": row["partner_country_iso3"],
        "partnerName": row["partner_country_name"],
        "toLat": _num(row["partner_latitude"]),
        "toLon": _num(row["partner_longitude"]),
        "direction": row["flow_direction"],
        "valueDaily": _num(row["value_usd_daily"]),
        "valueAnnual": _num(row["value_usd_annual"]),
        # Both are exposed so the panel can be honest about the gap: the
        # published total and the sum of the named industries do not always
        # agree, because coverage of the parts is uneven.
        "publishedTotal": _num(row["total_usd_daily"]),
        "industrySum": _num(row["industry_sum_usd_daily"]),
        "topIndustry": row["top_industry"] if row["is_industry_dominant"] else None,
        "topIndustryShare": _num(row["top_industry_share"]),
        "industryCount": row["industry_count"],
        "rank": row["value_rank"],
        "rankInPort": row["value_rank_in_port"],
        "rankInCountry": row["value_rank_in_country"],
        "industries": [
            {
                "name": b["industry_name"],
                "hsSection": b["hs_section"],
                "order": b["industry_order"],
                "valueDaily": _num(b["value_usd_daily"]),
                "valueAnnual": _num(b["value_usd_annual"]),
                "share": _num(b["share_of_link"]),
                "rank": b["industry_rank"],
            }
            for b in breakdown
        ],
    }


def ribbon(port_id: str, partner_iso3: str, direction: str) -> dict:
    """One flow: its value, and what goods make it up."""
    port_id = (port_id or "").strip()
    partner_iso3 = (partner_iso3 or "").strip().upper()
    direction = (direction or "").strip().lower()
    # Port-relative, not partner-relative: outbound leaves the quay, inbound
    # arrives at it. See stg_portwatch__trade_ribbons for why.
    if not port_id or len(partner_iso3) != 3 or direction not in ("inbound", "outbound"):
        return {"found": False}
    return _cached(
        ("maritime", "ribbon", port_id, partner_iso3, direction),
        lambda: _ribbon(port_id, partner_iso3, direction),
        ttl=_TTL,
    )


# ── Detail: a chokepoint ─────────────────────────────────────────────────────


def _chokepoint(chokepoint_id: str, days: int) -> dict:
    profile = _rows(
        f"""
        select chokepoint_id, chokepoint_name, chokepoint_full_name,
               country_iso3, country_name, latitude, longitude,
               industry_top1, industry_top2, industry_top3,
               recent_transits, prior_transits, year_ago_transits,
               recent_capacity_dwt, prior_capacity_dwt, year_ago_capacity_dwt,
               transits_change, capacity_change, capacity_change_year_on_year,
               recent_transits_container, recent_transits_tanker,
               recent_transits_dry_bulk, last_transit_date
        from marts.dim_chokepoint
        where chokepoint_id = {_marker(0)}
        """,
        [chokepoint_id],
    )
    if not profile:
        return {"chokepointId": chokepoint_id, "found": False}

    row = profile[0]

    history = _rows(
        f"""
        select transit_date, transits, capacity_dwt,
               transits_container, transits_tanker, transits_dry_bulk,
               capacity_dwt_container, capacity_dwt_tanker, capacity_dwt_dry_bulk,
               transits_7d_avg, capacity_dwt_7d_avg, capacity_dwt_year_ago
        from marts.fact_chokepoint_transits_daily
        where chokepoint_id = {_marker(0)}
        order by transit_date desc
        limit {_marker(1)}
        """,
        [chokepoint_id, days],
    )

    return {
        "chokepointId": row["chokepoint_id"],
        "found": True,
        "name": row["chokepoint_name"],
        "fullName": row["chokepoint_full_name"],
        "iso3": row["country_iso3"],
        "country": row["country_name"],
        "lat": _num(row["latitude"]),
        "lon": _num(row["longitude"]),
        "industries": [
            value
            for value in (row["industry_top1"], row["industry_top2"], row["industry_top3"])
            if value
        ],
        "transits": _num(row["recent_transits"]),
        "priorTransits": _num(row["prior_transits"]),
        "yearAgoTransits": _num(row["year_ago_transits"]),
        "capacity": _num(row["recent_capacity_dwt"]),
        "priorCapacity": _num(row["prior_capacity_dwt"]),
        "yearAgoCapacity": _num(row["year_ago_capacity_dwt"]),
        "transitsChange": _num(row["transits_change"]),
        "capacityChange": _num(row["capacity_change"]),
        "capacityChangeYoY": _num(row["capacity_change_year_on_year"]),
        "containerTransits": _num(row["recent_transits_container"]),
        "tankerTransits": _num(row["recent_transits_tanker"]),
        "dryBulkTransits": _num(row["recent_transits_dry_bulk"]),
        "asOf": _date(row["last_transit_date"]),
        "history": [
            {
                "date": _date(h["transit_date"]),
                "transits": _num(h["transits"]),
                "capacity": _num(h["capacity_dwt"]),
                "container": _num(h["transits_container"]),
                "tanker": _num(h["transits_tanker"]),
                "dryBulk": _num(h["transits_dry_bulk"]),
                "transitsTrend": _num(h["transits_7d_avg"]),
                "capacityTrend": _num(h["capacity_dwt_7d_avg"]),
                "capacityYearAgo": _num(h["capacity_dwt_year_ago"]),
            }
            for h in reversed(history)
        ],
    }


def chokepoint(chokepoint_id: str, days: int = 900) -> dict:
    """One chokepoint: transits and deadweight, daily, with a year-ago line."""
    chokepoint_id = (chokepoint_id or "").strip()
    if not chokepoint_id:
        return {"chokepointId": chokepoint_id, "found": False}
    return _cached(
        ("maritime", "chokepoint", chokepoint_id, days),
        lambda: _chokepoint(chokepoint_id, days),
        ttl=_TTL,
    )


# ── Detail: a country ────────────────────────────────────────────────────────


def _country(iso3: str, weeks: int) -> dict:
    ports = _rows(
        f"""
        select port_id, port_name, latitude, longitude,
               recent_tons, tons_change, recent_import_tons, recent_export_tons,
               industry_top1, tonnage_rank, tonnage_rank_in_country,
               share_country_maritime_import, share_country_maritime_export
        from marts.dim_port
        where country_iso3 = {_marker(0)}
        order by coalesce(recent_tons, 0) desc
        """,
        [iso3],
    )

    # The country's own tonnage series, summed across its ports. Done here rather
    # than in a mart because it is one group-by over an already-aggregated
    # weekly table, and a per-country mart would be a fourth copy of the same
    # numbers.
    history = _rows(
        f"""
        select week_start,
               sum(total_tons)  as total_tons,
               sum(import_tons) as import_tons,
               sum(export_tons) as export_tons,
               sum(port_calls)  as port_calls
        from marts.fact_port_activity_weekly
        where country_iso3 = {_marker(0)}
        group by week_start
        order by week_start desc
        limit {_marker(1)}
        """,
        [iso3, weeks],
    )

    links = _rows(
        f"""
        select partner_country_iso3, partner_country_name, flow_direction,
               sum(value_usd_daily) as value_daily,
               count(*)             as port_count
        from marts.fact_trade_ribbon
        where port_country_iso3 = {_marker(0)}
        group by partner_country_iso3, partner_country_name, flow_direction
        order by sum(value_usd_daily) desc
        limit 30
        """,
        [iso3],
    )

    mix = _rows(
        f"""
        select industry_name, flow_direction,
               sum(value_usd_daily) as value_daily
        from marts.fact_trade_ribbon_industry
        where port_country_iso3 = {_marker(0)}
        group by industry_name, flow_direction
        order by sum(value_usd_daily) desc
        """,
        [iso3],
    )

    return {
        "iso3": iso3,
        "found": bool(ports),
        "ports": [
            {
                "portId": p["port_id"],
                "name": p["port_name"],
                "lat": _num(p["latitude"]),
                "lon": _num(p["longitude"]),
                "tons": _num(p["recent_tons"]),
                "change": _num(p["tons_change"]),
                "importTons": _num(p["recent_import_tons"]),
                "exportTons": _num(p["recent_export_tons"]),
                "topIndustry": p["industry_top1"],
                "rank": p["tonnage_rank"],
                "rankInCountry": p["tonnage_rank_in_country"],
                "shareOfImports": _num(p["share_country_maritime_import"]),
                "shareOfExports": _num(p["share_country_maritime_export"]),
            }
            for p in ports
        ],
        "history": [
            {
                "week": _date(h["week_start"]),
                "tons": _num(h["total_tons"]),
                "importTons": _num(h["import_tons"]),
                "exportTons": _num(h["export_tons"]),
                "portCalls": _num(h["port_calls"]),
            }
            for h in reversed(history)
        ],
        "partners": [
            {
                "iso3": link["partner_country_iso3"],
                "name": link["partner_country_name"],
                "direction": link["flow_direction"],
                "valueDaily": _num(link["value_daily"]),
                "valueAnnual": (_num(link["value_daily"]) or 0) * 365,
                "portCount": link["port_count"],
            }
            for link in links
        ],
        "industryMix": [
            {
                "name": m["industry_name"],
                "direction": m["flow_direction"],
                "valueDaily": _num(m["value_daily"]),
            }
            for m in mix
        ],
    }


def country(iso3: str, weeks: int = 260) -> dict:
    """One country's seaborne trade: its ports, its tonnage, who it ships to."""
    iso3 = (iso3 or "").strip().upper()
    if len(iso3) != 3:
        return {"iso3": iso3, "found": False}
    return _cached(("maritime", "country", iso3, weeks), lambda: _country(iso3, weeks), ttl=_TTL)
