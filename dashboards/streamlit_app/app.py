"""Kubera_EDW — Streamlit BI app (Phase 7).

A lightweight alternative to Metabase: reads the modeled warehouse (DuckDB/Postgres) and renders
the 3-5 dashboards mapped to the KPI framework (project_spec.md §10):
  - Portfolio allocation (country / sector / currency)
  - Holding fundamentals (revenue growth, EBITDA margin, net income)
  - Market performance (USD-normalized total return, volatility/drawdown, vs. benchmark)
  - FX contribution to return
  - Macro overlay (GDP/inflation) + gold price vs. portfolio return

Run: streamlit run dashboards/streamlit_app/app.py
"""

from __future__ import annotations

import streamlit as st


def main() -> None:
    st.set_page_config(page_title="Kubera_EDW", layout="wide")
    st.title("Kubera Global Asset Management — EDW")
    st.caption("Fictional firm; real public data. No investment advice implied.")
    st.info("🚧 Dashboards not yet built. Implement in Phase 7 once the warehouse is populated.")
    # TODO: connect to warehouse (duckdb.connect(DUCKDB_PATH) or psycopg to Postgres),
    #       query the marts, and render the KPI dashboards above.


if __name__ == "__main__":
    main()
