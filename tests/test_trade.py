"""Bilateral trade and trade composition.

Nothing here reaches the network. The parts worth pinning are the ones that
would produce a plausible wrong answer rather than an error: WITS indexes its
partner codes positionally, its aggregates share the ISO3 namespace with real
countries, and an older observation must never overwrite a newer one.
"""

from __future__ import annotations

import json

from dashboard_hub.lib import trade


def _sdmx(partners: list[str], values: dict[str, float]) -> dict:
    """A WITS response shaped like the real one, for the given partners."""
    return {
        "structure": {
            "dimensions": {
                "series": [
                    {"id": "FREQ", "values": [{"id": "A"}]},
                    {"id": "REPORTER", "values": [{"id": "JPN"}]},
                    {"id": "PARTNER", "values": [{"id": p} for p in partners]},
                    {"id": "PRODUCTCODE", "values": [{"id": "Total"}]},
                    {"id": "INDICATOR", "values": [{"id": "XPRT-TRD-VL"}]},
                ]
            }
        },
        "dataSets": [
            {
                "series": {
                    f"0:0:{i}:0:0": {"observations": {"0": [values[p], 0]}}
                    for i, p in enumerate(partners)
                    if p in values
                }
            }
        ],
    }


def test_partner_codes_are_read_from_the_structure(monkeypatch):
    """The series key indexes into the dimension list — a mismatch swaps countries."""
    payload = _sdmx(["CHN", "USA", "KOR"], {"CHN": 144.5, "USA": 139.8, "KOR": 54.0})
    monkeypatch.setattr(trade, "_fetch", lambda url: payload)

    flows = trade._wits_flow("JPN", 2022, "XPRT-TRD-VL")
    # Values arrive in thousands of USD.
    assert flows == {
        "CHN": 144.5 * 1000,
        "USA": 139.8 * 1000,
        "KOR": 54.0 * 1000,
    }


def test_zero_and_missing_observations_are_dropped(monkeypatch):
    payload = _sdmx(["CHN", "USA"], {"CHN": 0.0, "USA": 10.0})
    monkeypatch.setattr(trade, "_fetch", lambda url: payload)
    assert set(trade._wits_flow("JPN", 2022, "XPRT-TRD-VL")) == {"USA"}


def test_a_dead_feed_is_empty_not_an_exception(monkeypatch):
    monkeypatch.setattr(trade, "_fetch", lambda url: None)
    assert trade._wits_flow("JPN", 2022, "XPRT-TRD-VL") == {}


def test_aggregates_never_reach_the_partner_list(monkeypatch):
    """WLD, EAS and NAC share the ISO3 namespace and would top every ranking."""
    exports = {"WLD": 746_672_097_000, "EAS": 372_291_738_000, "CHN": 144_539_096_000}
    imports = {"WLD": 898_000_000_000, "CHN": 188_900_000_000}
    monkeypatch.setattr(
        trade,
        "_wits_flow",
        lambda iso3, year, indicator: exports if indicator == "XPRT-TRD-VL" else imports,
    )
    monkeypatch.setattr(trade, "_countries", lambda: {"CHN": "China", "JPN": "Japan"})

    result = trade._partners("JPN")
    assert [p["iso3"] for p in result["partners"]] == ["CHN"]
    # The world total is still kept — it is the denominator, not a counterparty.
    assert result["totalExports"] == 746_672_097_000
    assert result["totalImports"] == 898_000_000_000


def test_the_reporter_is_not_its_own_partner(monkeypatch):
    monkeypatch.setattr(
        trade, "_wits_flow", lambda iso3, year, indicator: {"JPN": 5.0, "CHN": 10.0}
    )
    monkeypatch.setattr(trade, "_countries", lambda: {"CHN": "China", "JPN": "Japan"})
    assert [p["iso3"] for p in trade._partners("JPN")["partners"]] == ["CHN"]


def test_balance_signs_follow_the_reporter(monkeypatch):
    """Positive means the reporter sells more than it buys."""
    monkeypatch.setattr(
        trade,
        "_wits_flow",
        lambda iso3, year, indicator: (
            {"USA": 139_000.0, "AUS": 16_000.0}
            if indicator == "XPRT-TRD-VL"
            else {"USA": 90_000.0, "AUS": 88_000.0}
        ),
    )
    monkeypatch.setattr(
        trade, "_countries", lambda: {"USA": "United States", "AUS": "Australia", "JPN": "Japan"}
    )

    rows = {p["iso3"]: p for p in trade._partners("JPN")["partners"]}
    assert rows["USA"]["balance"] > 0, "Japan sells more to the US than it buys"
    assert rows["AUS"]["balance"] < 0, "Japan buys more from Australia than it sells"


def test_a_year_with_no_data_falls_back_to_the_one_before(monkeypatch):
    calls: list[int] = []

    def flow(iso3, year, indicator):
        calls.append(year)
        return {"CHN": 1.0} if year == trade._LATEST_YEAR - 1 else {}

    monkeypatch.setattr(trade, "_wits_flow", flow)
    monkeypatch.setattr(trade, "_countries", lambda: {"CHN": "China"})

    assert trade._partners("JPN")["year"] == trade._LATEST_YEAR - 1


def test_composition_keeps_the_newest_year_per_category(monkeypatch):
    """The date-window path returns several years; an older one must not win."""

    def wb_all(code: str):
        if code != "TX.VAL.MANF.ZS.UN":
            return []
        return [
            {"countryiso3code": "JPN", "date": "2020", "value": 70.0},
            {"countryiso3code": "JPN", "date": "2023", "value": 80.6},
            {"countryiso3code": "JPN", "date": "2021", "value": 75.0},
        ]

    monkeypatch.setattr(trade, "_wb_all", wb_all)
    world = trade._composition_world()

    assert world["JPN"]["exports"] == [
        {"key": "manufactures", "label": "Manufactures", "share": 80.6}
    ]
    assert world["JPN"]["years"]["exports"] == 2023


def test_composition_is_sorted_by_share(monkeypatch):
    table = {
        "TX.VAL.FUEL.ZS.UN": [{"countryiso3code": "SAU", "date": "2023", "value": 79.4}],
        "TX.VAL.MANF.ZS.UN": [{"countryiso3code": "SAU", "date": "2023", "value": 15.9}],
        "TX.VAL.FOOD.ZS.UN": [{"countryiso3code": "SAU", "date": "2023", "value": 1.9}],
    }
    monkeypatch.setattr(trade, "_wb_all", lambda code: table.get(code, []))

    shares = trade._composition_world()["SAU"]["exports"]
    assert [s["key"] for s in shares] == ["fuel", "manufactures", "food"]


def test_an_unknown_country_returns_a_blank_rather_than_raising(monkeypatch):
    monkeypatch.setattr(trade, "composition_world", dict)
    assert trade.composition("ZZZ") == {"iso3": "ZZZ", "exports": [], "imports": [], "years": {}}
    assert trade.composition("")["exports"] == []


def test_a_thin_world_pull_is_not_cached(monkeypatch, tmp_path):
    """A half-answered walk would otherwise be served for a week."""
    monkeypatch.setattr(trade, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(trade, "_composition_world", lambda: {"JPN": {}})

    trade.composition_world()
    assert not (tmp_path / "composition_world.json").exists()


def test_a_full_world_pull_is_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(trade, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        trade, "_composition_world", lambda: {f"C{i}": {"exports": []} for i in range(150)}
    )

    trade.composition_world()
    written = json.loads((tmp_path / "composition_world.json").read_text())
    assert len(written["data"]) == 150
