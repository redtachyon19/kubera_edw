"""The world desk — governments, currencies and global sectors.

Nothing here reaches the network. The pieces that matter are the ones that
silently produce a wrong number rather than an error: an inverted FX pair read
the wrong way up, an older World Bank row overwriting a newer one, or a narrow
warehouse being mistaken for a world view.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from dashboard_hub.lib import world

# ── Reference table ──────────────────────────────────────────────────────────


def test_every_index_country_has_a_currency():
    """A market with no currency cannot be compared in dollars."""
    missing = sorted(set(world.INDICES) - set(world.CURRENCIES))
    assert missing == [], f"no currency mapped for {missing}"


def test_euro_members_share_one_pair():
    """Nineteen governments, one exchange rate — and it is the inverted one."""
    for iso3 in ("DEU", "FRA", "ITA", "NLD"):
        assert world.CURRENCIES[iso3]["code"] == "EUR"
        assert world.CURRENCIES[iso3]["symbol"] == "EURUSD=X"
        assert world.CURRENCIES[iso3]["invert"] is True


def test_the_dollar_is_its_own_base():
    assert world.CURRENCIES["USA"]["symbol"] is None


def test_reference_file_covers_the_world():
    countries = world.reference()
    assert len(countries) > 150
    assert all(c["lat"] is not None and c["lon"] is not None for c in countries)

    by_iso3 = {c["iso3"]: c for c in countries}
    # Every country the desk can chart a market for has to be drawable.
    for iso3 in world.INDICES:
        assert iso3 in by_iso3, f"{iso3} has an index but no coordinates"

    for country in countries:
        assert -90 <= country["lat"] <= 90
        assert -180 <= country["lon"] <= 180


def test_land_outline_is_bundled_and_drawable():
    """The globe cannot draw continents it does not ship with."""
    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "dashboard_hub"
        / "hub"
        / "src"
        / "components"
        / "land.json"
    )
    rings = json.loads(path.read_text())

    assert len(rings) > 20, "too few rings to be a world"
    for ring in rings:
        assert len(ring) >= 4, "a ring needs at least a triangle plus its close"
        for lon, lat in ring:
            assert -180 <= lon <= 180
            assert -90 <= lat <= 90


def test_simplify_keeps_the_shape_and_drops_the_padding():
    """RDP must remove collinear filler and keep the vertex that carries the bend."""
    from scripts.generate_land_outline import simplify

    # A straight run east, then a sharp turn north.
    straight = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0), (4.0, 0.0)]
    assert simplify(straight, 0.5) == [(0.0, 0.0), (4.0, 0.0)]

    bent = [(0.0, 0.0), (1.0, 0.0), (2.0, 5.0), (3.0, 0.0), (4.0, 0.0)]
    thinned = simplify(bent, 0.5)
    assert (2.0, 5.0) in thinned, "the corner is the whole point of the coastline"
    assert thinned[0] == (0.0, 0.0) and thinned[-1] == (4.0, 0.0)


def test_simplify_leaves_short_rings_alone():
    from scripts.generate_land_outline import simplify

    tiny = [(0.0, 0.0), (1.0, 1.0)]
    assert simplify(tiny, 5.0) == tiny


def test_global_sectors_are_one_per_gics_sector():
    assert len(world.GLOBAL_SECTORS) == 10
    assert len({s["symbol"] for s in world.GLOBAL_SECTORS}) == 10
    assert len({s["slug"] for s in world.GLOBAL_SECTORS}) == 10


# ── FX direction ─────────────────────────────────────────────────────────────


@pytest.fixture
def moves(monkeypatch):
    """Stand in for Yahoo with a fixed set of quotes."""

    def install(table: dict[str, dict]):
        monkeypatch.setattr(world, "_returns", lambda symbols, period: table)

    return install


def test_direct_pair_reads_straight_through(moves):
    """`JPY=X` is yen per dollar: a rising pair is a weakening yen."""
    moves({"JPY=X": {"last": 150.0, "change": 0.10, "asOf": "2026-08-03"}})
    fx = world._fx("1Y")

    assert fx["JPY"]["perUsd"] == pytest.approx(150.0)
    # Ten percent more yen to the dollar leaves the yen down ~9.1%, not down 10%.
    assert fx["JPY"]["change"] == pytest.approx(1 / 1.10 - 1)
    assert fx["JPY"]["change"] < 0


def test_inverted_pair_is_flipped(moves):
    """`GBPUSD=X` is dollars per pound: a rising pair is a strengthening pound."""
    moves({"GBPUSD=X": {"last": 1.25, "change": 0.08, "asOf": "2026-08-03"}})
    fx = world._fx("1Y")

    assert fx["GBP"]["perUsd"] == pytest.approx(0.8)
    assert fx["GBP"]["change"] == pytest.approx(0.08)


def test_the_dollar_never_moves_against_itself(moves):
    moves({})
    fx = world._fx("1Y")
    assert fx["USD"] == {"perUsd": 1.0, "change": 0.0, "symbol": None}


def test_a_currency_yahoo_has_nothing_for_is_absent(moves):
    """Absent, not zero — the desk must be able to say it has no reading."""
    moves({})
    assert "JPY" not in world._fx("1Y")


# ── World Bank reduction ─────────────────────────────────────────────────────


def _row(iso3: str, year: int, value: float) -> dict:
    return {"countryiso3code": iso3, "date": str(year), "value": value}


def test_newest_year_wins_regardless_of_order(monkeypatch):
    """The date-window path returns several years per country, in any order."""
    monkeypatch.setattr(
        world,
        "_wb_indicator",
        lambda code: (
            [
                _row("USA", 2023, 4.1),
                _row("USA", 2025, 2.9),
                _row("USA", 2024, 3.4),
            ]
            if code == world._WB_INDICATORS["inflation"]
            else []
        ),
    )

    macro = world._world_bank_live()
    assert macro["USA"]["inflation"] == pytest.approx(2.9)
    assert macro["USA"]["inflationYear"] == 2025


def test_indicators_keep_their_own_years(monkeypatch):
    """Unemployment lands a year behind inflation; both years must survive."""
    table = {
        world._WB_INDICATORS["inflation"]: [_row("USA", 2025, 2.9)],
        world._WB_INDICATORS["unemployment"]: [_row("USA", 2024, 4.2)],
        world._WB_INDICATORS["gdpGrowth"]: [],
    }
    monkeypatch.setattr(world, "_wb_indicator", lambda code: table.get(code, []))

    macro = world._world_bank_live()
    assert macro["USA"]["inflationYear"] == 2025
    assert macro["USA"]["unemploymentYear"] == 2024
    # The headline year is the newest of them, not the oldest.
    assert macro["USA"]["year"] == 2025


def test_rows_without_a_value_are_skipped(monkeypatch):
    monkeypatch.setattr(
        world,
        "_wb_indicator",
        lambda code: [{"countryiso3code": "ZWE", "date": "2025", "value": None}],
    )
    assert world._world_bank_live() == {}


def test_a_narrow_warehouse_falls_back_to_the_world_bank(monkeypatch):
    """Thirteen countries is a portfolio, not a world — ask the source instead."""
    monkeypatch.setattr(
        world.warehouse,
        "macro",
        lambda *args, **kwargs: [
            {"country_iso3": f"C{i}", "calendar_year": 2025} for i in range(13)
        ],
    )
    called: list[bool] = []
    monkeypatch.setattr(
        world,
        "_macro_live_cached",
        lambda: called.append(True) or {"USA": {"inflation": 2.9, "year": 2025}},
    )

    assert world._macro_by_country()["USA"]["inflation"] == pytest.approx(2.9)
    assert called == [True]


def test_a_wide_warehouse_answers_for_itself(monkeypatch):
    rows = [
        {
            "country_iso3": f"C{i}",
            "calendar_year": year,
            "cpi_inflation_pct": 2.0 + i,
            "gdp_growth_pct": 1.0,
            "unemployment_pct": 5.0,
            "gdp": None,
        }
        for i in range(60)
        for year in (2024, 2025)
    ]
    monkeypatch.setattr(world.warehouse, "macro", lambda *args, **kwargs: rows)
    monkeypatch.setattr(
        world, "_macro_live_cached", lambda: pytest.fail("should not have gone to the network")
    )

    macro = world._macro_by_country()
    assert len(macro) == 60
    assert macro["C0"]["year"] == 2025
    assert macro["C0"]["priorInflation"] == pytest.approx(2.0)


# ── Disk cache ───────────────────────────────────────────────────────────────


def test_a_stale_cache_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "world_macro_cache.json"
    path.write_text(json.dumps({"fetchedAt": 0, "data": {"USA": {"inflation": 2.0}}}))
    monkeypatch.setattr(world, "_cache_path", lambda: path)

    assert world._read_cache() is None


def test_a_thin_cache_is_ignored(tmp_path, monkeypatch):
    """A cached pull that only half-succeeded must not be served for a day."""
    import time

    path = tmp_path / "world_macro_cache.json"
    path.write_text(json.dumps({"fetchedAt": time.time(), "data": {"USA": {"inflation": 2.0}}}))
    monkeypatch.setattr(world, "_cache_path", lambda: path)

    assert world._read_cache() is None


def test_a_good_cache_round_trips(tmp_path, monkeypatch):
    path = tmp_path / "world_macro_cache.json"
    monkeypatch.setattr(world, "_cache_path", lambda: path)

    data = {f"C{i}": {"inflation": float(i), "year": 2025} for i in range(50)}
    world._write_cache(data)

    assert world._read_cache() == data


def test_a_missing_cache_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(world, "_cache_path", lambda: tmp_path / "absent.json")
    assert world._read_cache() is None


# ── Assembly ─────────────────────────────────────────────────────────────────


def test_snapshot_joins_macro_fx_and_markets(monkeypatch):
    monkeypatch.setattr(
        world,
        "reference",
        lambda: [
            {
                "iso3": "JPN",
                "name": "Japan",
                "region": "Asia-Pacific",
                "incomeLevel": "High income",
                "capital": "Tokyo",
                "lat": 35.67,
                "lon": 139.75,
            },
            {
                "iso3": "TCD",
                "name": "Chad",
                "region": "Africa",
                "incomeLevel": "Low income",
                "capital": "N'Djamena",
                "lat": 12.11,
                "lon": 15.05,
            },
        ],
    )
    monkeypatch.setattr(
        world, "_macro_by_country", lambda: {"JPN": {"inflation": 3.17, "year": 2025}}
    )
    monkeypatch.setattr(world, "_fx", lambda period: {"JPY": {"perUsd": 157.0, "change": -0.06}})
    monkeypatch.setattr(
        world, "_returns", lambda symbols, period: {"^N225": {"change": 0.59, "last": 52000.0}}
    )
    monkeypatch.setattr(world.warehouse, "holdings", lambda: {"7203.T": {"country_iso3": "JPN"}})
    monkeypatch.setattr(world, "_macro_from_warehouse", lambda: False)

    snapshot = world._snapshot("1Y")
    japan, chad = snapshot["countries"][1], snapshot["countries"][0]

    assert japan["name"] == "Japan"
    assert japan["inflation"] == pytest.approx(3.17)
    assert japan["fxPerUsd"] == pytest.approx(157.0)
    assert japan["index"] == "Nikkei 225"
    assert japan["marketChange"] == pytest.approx(0.59)
    assert japan["hasIssuer"] is True

    # A country with no market and no currency still keeps its place on the
    # globe — it just has nothing to report.
    assert chad["name"] == "Chad"
    assert chad["currency"] is None
    assert chad["marketChange"] is None
    assert chad["hasIssuer"] is False

    assert snapshot["macroYear"] == 2025
    assert snapshot["macroSource"] == "World Bank, live"


def test_sectors_come_back_ranked(monkeypatch):
    monkeypatch.setattr(
        world,
        "_returns",
        lambda symbols, period: {
            symbol: {"change": change, "last": 100.0, "asOf": "2026-08-03"}
            for symbol, change in (
                ("IXN", 0.41),
                ("IXC", 0.43),
                ("IXG", 0.23),
                ("SPY", 0.21),
                ("ILF", 0.46),
            )
        },
    )

    payload = world._sectors("1Y")
    assert [s["symbol"] for s in payload["sectors"]] == ["IXC", "IXN", "IXG"]
    assert [r["symbol"] for r in payload["regions"]] == ["ILF", "SPY"]
    # Symbols Yahoo had nothing for are dropped, not rendered as flat.
    assert all(s["change"] is not None for s in payload["sectors"])


# ── Gold as the unit of account ──────────────────────────────────────────────


def _flat(values, start="2021-01-01"):
    import pandas as pd

    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"))


def test_rebase_starts_at_one_hundred():
    rows = world._rebase(_flat([50.0, 75.0, 100.0]))
    assert rows[0]["value"] == pytest.approx(100.0)
    assert rows[-1]["value"] == pytest.approx(200.0)


def test_a_currency_that_holds_against_gold_reads_flat(monkeypatch):
    """Gold flat and the peg flat means purchasing power flat — no drift."""
    monkeypatch.setattr(
        world,
        "_series",
        lambda symbol, period: _flat([100.0] * 5) if symbol == world.GOLD else _flat([2.0] * 5),
    )
    monkeypatch.setitem(
        world.CURRENCIES, "XXX", {"code": "XXX", "symbol": "XXX=X", "invert": False}
    )

    result = world._purchasing_power("XXX", "1Y")
    assert result["goldChange"] == pytest.approx(0.0)


def test_gold_doubling_halves_what_the_currency_buys(monkeypatch):
    monkeypatch.setattr(
        world,
        "_series",
        lambda symbol, period: (
            _flat([100.0, 150.0, 200.0]) if symbol == world.GOLD else _flat([1.0, 1.0, 1.0])
        ),
    )
    monkeypatch.setitem(
        world.CURRENCIES, "XXX", {"code": "XXX", "symbol": "XXX=X", "invert": False}
    )

    result = world._purchasing_power("XXX", "1Y")
    assert result["goldChange"] == pytest.approx(-0.5)


def test_a_weakening_currency_loses_more_in_gold_than_against_the_dollar(monkeypatch):
    """The point of the whole panel: the dollar is measured, not the ruler."""
    # Gold doubles in dollars, and the currency halves against the dollar.
    monkeypatch.setattr(
        world,
        "_series",
        lambda symbol, period: (
            _flat([100.0, 150.0, 200.0]) if symbol == world.GOLD else _flat([1.0, 1.5, 2.0])
        ),
    )
    monkeypatch.setitem(
        world.CURRENCIES, "XXX", {"code": "XXX", "symbol": "XXX=X", "invert": False}
    )

    result = world._purchasing_power("XXX", "1Y")
    assert result["usdChange"] == pytest.approx(-0.5)
    # Down half against the dollar and the dollar down half against gold: a
    # quarter of the gold it started with.
    assert result["goldChange"] == pytest.approx(-0.75)
    assert result["dollarGoldChange"] == pytest.approx(-0.5)


def test_the_dollar_is_not_drawn_twice(monkeypatch):
    """For the USA, `in gold` and `USD in gold` are the same series."""
    monkeypatch.setattr(world, "_series", lambda symbol, period: _flat([100.0, 110.0, 120.0]))

    result = world._purchasing_power("USA", "1Y")
    assert [line["key"] for line in result["lines"]] == ["inGold"]


def test_no_gold_price_means_no_chart(monkeypatch):
    monkeypatch.setattr(world, "_series", lambda symbol, period: None)
    assert world._purchasing_power("JPN", "1Y")["points"] == []


# ── News ─────────────────────────────────────────────────────────────────────


def test_headlines_drop_the_publisher_suffix():
    """Google appends " - Publisher" to every title; it is already a field."""
    xml = """<rss><channel><item>
      <title>Bank of Japan holds rates - Reuters</title>
      <link>https://example.test/a</link>
      <source url="https://reuters.com">Reuters</source>
      <pubDate>Mon, 03 Aug 2026 09:00:00 GMT</pubDate>
    </item></channel></rss>"""

    class _Response:
        def read(self):
            return xml.encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    import urllib.request

    original = urllib.request.urlopen
    urllib.request.urlopen = lambda *a, **k: _Response()
    try:
        stories = world._country_news("Japan", 5)
    finally:
        urllib.request.urlopen = original

    assert stories[0]["title"] == "Bank of Japan holds rates"
    assert stories[0]["source"] == "Reuters"


def test_cdata_and_entities_are_decoded():
    block = "<title><![CDATA[Oil &amp; gas &lt;up&gt;]]></title>"
    assert world._tag(block, "title") == "Oil & gas <up>"


def test_a_dead_news_feed_is_an_empty_list(monkeypatch):
    import urllib.request

    def boom(*args, **kwargs):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert world._country_news("Japan", 5) == []


# ── Energy ───────────────────────────────────────────────────────────────────


def test_energy_covers_both_gas_benchmarks():
    """Henry Hub and TTF price the same molecule on two continents."""
    slugs = {entry["slug"] for entry in world.ENERGY}
    assert {"henry-hub", "ttf", "wti", "brent"} <= slugs


def test_energy_symbols_are_unique():
    symbols = [entry["symbol"] for entry in world.ENERGY]
    assert len(symbols) == len(set(symbols))


def test_energy_drops_instruments_yahoo_has_nothing_for(monkeypatch):
    monkeypatch.setattr(
        world, "_returns", lambda symbols, period: {"CL=F": {"last": 80.0, "change": 0.2}}
    )
    monkeypatch.setattr(world, "_series", lambda symbol, period: None)

    panel = world._energy("1Y")
    assert [row["slug"] for row in panel["prices"]] == ["wti"]
