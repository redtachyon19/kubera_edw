# notes_for_red.md

**Known issues, limitations and incomplete work.**

This is a problem inventory, not a plan — it records *what does not work and why*, deliberately
without proposed solutions. Every claim below was verified against the built warehouse or a live
API call, not assumed. Written 2026-07-24; revised 2026-07-25 after the Phase-8 scale-out to
38 companies (one item resolved, several re-measured at the new scale).

Status shorthand: **BLOCKER** (wrong or misleading output) · **LIMITATION** (works, but bounded)
· **INCOMPLETE** (specified, not built) · **RISK** (fine now, will break later).

---

## 1. Market price history

### 1.1 Only ~100 trading days of price history exist — LIMITATION
`fact_market_prices` covers **2026-03-03 → 2026-07-24 (100 days)**. Alpha Vantage moved
`outputsize=full` to its premium tier, so the free `TIME_SERIES_DAILY` endpoint returns only the
latest ~100 points. Volatility and drawdown are computed over a ~5-month window, which is too
short to characterise a holding. Multi-year total return — the headline KPI in §10 — is not
computable at all.

### 1.2 A one-time historical load would be destroyed by the next scheduled run — BLOCKER
`BaseClient._land()` writes a **fixed filename per ticker** (`av_AAPL.json`). Any subsequent
`compact` fetch overwrites the file in place. If a full history were ever pulled, the first daily
run afterwards would silently replace 20 years with 100 days. There is no archive, no append, no
merge, and no dedupe on `(ticker, trade_date)`.

### 1.3 Free-tier prices are NOT split/dividend adjusted — BLOCKER for long histories
The free `TIME_SERIES_DAILY` payload contains only `open/high/low/close/volume` — confirmed from
landed data; there is **no `adjusted_close`**. Corporate actions therefore appear as price
discontinuities: Apple's 4:1 (2020) and 7:1 (2014) splits would read as −75% and −86% single-day
returns. Over the current 100-day window no split has occurred, so today's numbers are clean —
but any split during a future free-tier period corrupts the return series from that day forward,
and nothing in the pipeline detects it.

### 1.4 Benchmarks are extracted but never modelled — INCOMPLETE
SPY and ACWI are configured in `companies.yml`, fetched, and land in `raw.market_prices`
(1,200 rows vs 900 in the fact). They are then **dropped**: `fact_market_prices` filters on
`is_held_position`, and no benchmark fact or relative-performance measure exists. "Relative
performance vs. sector peers" and benchmark comparison (§10) are unimplemented.

### 1.5 Alpha Vantage's daily cap is now genuinely binding — LIMITATION
~25 requests/day and ~1 request/second, against a universe of 38 companies + 2 benchmarks + the
gold proxy = 41 tickers. A per-run budget (`PRICES_REQUEST_BUDGET`, default 20) defers the
overflow so runs degrade predictably instead of failing the tail, and the freshness cache means
a cached ticker costs nothing. **Price coverage therefore fills in across runs rather than being
complete after any single one — currently 34 of 38 companies.**

### 1.6 The request budget is per-run, not per-day — LIMITATION
The budget bounds a single invocation. Two runs on the same day can still exceed the ~25/day
account limit, which is what produced 4 failed tickers on the second Phase-8 run. Nothing tracks
cumulative daily spend across invocations.

---

## 2. Gold benchmark

### 2.1 The specified source no longer exists — LIMITATION
FRED series `GOLDAMGBD228NLBM` (LBMA daily fixing, the §5 primary source) returns
`400 "Bad Request. The series does not exist."` with a valid key. A FRED search for "gold price"
returns only volatility indices (`GVZCLS`) and producer/import price indices — **FRED no longer
publishes any spot USD/oz gold series**.

### 2.2 The substitute is a proxy, not the fixing — LIMITATION
Gold now uses **GLD (SPDR Gold Shares)** via Alpha Vantage. GLD is an ETF holding physical
bullion at roughly 1/10 troy oz per share, and its ratio to spot **drifts downward over time** as
the fund's expense ratio is paid out of holdings. It tracks gold; it is not gold. The column is
named `gold_price_usd` (not `_per_oz`) precisely because the values are ~$372/share against spot
of ~$3,720/oz — but any analysis treating it as a spot price is wrong.

### 2.3 Gold inherits every price-tier limitation — LIMITATION
Because it now flows through Alpha Vantage, gold has the same ~100-day window (§1.1), the same
overwrite problem (§1.2), and consumes one of the ~25 daily requests.

### 2.4 metals-api was never implemented — INCOMPLETE
Named in §5 as the backup for true spot, and `METALS_API_KEY` is still listed in `.env.example`.
No client code references it. The variable is dead configuration.

### 2.5 The gold-vs-portfolio overlay does not exist — INCOMPLETE
§10's KPI is "gold price trend **vs. portfolio return**". The dashboard plots gold alone. No
comparison, indexing to a common base, or correlation is implemented.

---

## 3. FRED

### 3.1 The FRED key is now unused — INCOMPLETE
Gold was FRED's only consumer, and it has moved to Alpha Vantage. `FRED_API_KEY` is configured
and valid but **nothing reads it**. §5 assigns FRED a second role — "U.S. macro indicators and
rates … the USD-denominated benchmark series against which other countries are compared" — and
no rates series (e.g. Treasury yields) is extracted.

---

## 4. Portfolio modelling — the largest structural gap

### 4.1 There are no position weights — BLOCKER for portfolio-level KPIs
*(Unchanged by the scale-out — now spread across 38 companies instead of 9.)*
The warehouse holds **no share counts, no cost basis, no entry dates, no position sizes**. The
allocation dashboard uses an equal-weight assumption (labelled as such in the UI). Consequences:

- Portfolio-level return **cannot be computed at all** — only per-holding returns exist.
- "Allocation % by country / sector / currency" (§10) is a count of holdings, not an exposure.
- Market-cap weighting is also unavailable — it needs shares outstanding, which is not extracted.

### 4.2 "FX contribution to return" is not what §10 asks for — LIMITATION
The FX Impact tab shows FX effects on **reported financials** (TM's JPY, BABA's CNY). The KPI in
§10 is FX contribution to *return*, which requires decomposing a position's total return into
local-currency return and currency movement. Every holding is a **US-listed ADR quoted in USD**,
so `close_price_local == close_price_usd` and the price-side FX contribution is structurally
zero. Measuring it properly would require home-market listings (e.g. Toyota on the TSE in JPY),
which are not sourced.

### 4.3 Entry thesis and over/under-performance are absent — INCOMPLETE
§4 asks "which positions are outperforming/underperforming their entry thesis, and by how much?"
There is no thesis, no entry price, no target, and no such measure anywhere in the model.

---

## 5. Financial statement coverage

### 5.1 EBITDA is missing from 43% of annual rows — LIMITATION
*(Re-measured at 38 companies. Revenue coverage is now complete at 38/38, but the derived and
secondary measures are not.)* EBITDA is operating income + D&A, and is **null for 233 of 545 FY
rows**; only **25 of 38 companies** have it at all, because the rest do not tag a
depreciation/amortisation concept the map recognises (D&A itself is null in 159/545 rows,
present for 29/38). Net debt / EBITDA inherits the gap, so any EBITDA-margin or leverage
comparison silently covers a subset.

### 5.2 Balance-sheet coverage is patchy — LIMITATION
`total_debt` is null in **220 of 545 FY rows** (present for 33/38 companies).
`cash_and_equivalents` is much better — null in only 49/545, present for all 38 — but net debt
requires both, so it inherits the debt gap.

### 5.3 Cost of revenue is missing for banks and several IFRS filers — LIMITATION
`cost_of_revenue` is null in **229 of 545 FY rows** (present for 26/38 companies), so gross
margin is unavailable for the rest. For a bank the concept is arguably not meaningful, but the
model does not distinguish "not applicable" from "not found" — both surface as null.

### 5.4 Headcount is never extracted — INCOMPLETE
§9 lists `headcount (where disclosed)` as a `fact_financials` measure. It is not in the concept
map and not in the table.

### 5.5 `industry` is empty for every company — INCOMPLETE
`dim_company.industry` exists per §9 but is **0/38 populated** — `companies.yml` carries `sector`
only. Any industry-level breakdown is impossible.

### 5.6 Five company-years fail quarterly-to-annual reconciliation — LIMITATION
The dbt test warns (does not fail) on: AZN 2017 (10.3% gap), AZN 2016 (7.3%), MSFT 2016 (6.4%),
AZN 2018 (4.1%), AZN 2019 (2.9%). AZN's are likely 6-K interim periods that are not true
quarters; MSFT 2016 is likely a restatement. **Neither has been investigated or confirmed** —
they are flagged and unexplained.

---

## 6. FX normalization

### 6.1 Nine fact rows have no USD conversion — LIMITATION
Frankfurter's history begins **2014-12-31**, but filings go back to 2007. `rate_per_usd` is null
for TM (7 rows, 2008-03-31 → 2014-03-31) and BABA (2 rows, 2013-03-31 → 2014-03-31), so
`revenue_usd`/`ebitda_usd` are null there. Those years are silently absent from any USD chart.

### 6.2 Carry-forward is capped at 7 days — LIMITATION
`fx_max_carry_forward_days: 7` bounds how far a rate is carried past the last published quote.
Correct for weekends and holidays, but a period end more than 7 days after the final quote gets
no rate at all. Rows using a carried rate are flagged (`fx_rate_carried_forward`), but nothing
consumes that flag downstream.

### 6.3 ~~Only two companies exercise conversion~~ — RESOLVED by the Phase-8 scale-out
Was: only TM (JPY) and BABA (CNY) converted, so the capability rested on 2 of 9 holdings. Now
**18 companies across 8 currencies** (EUR 4, JPY 4, CNY 3, GBP 2, KRW 2, MXN 1, BRL 1, INR 1).
The remaining nuance is that 12 of 38 companies file in a currency other than their domicile's
— mostly foreign issuers filing in USD — so domicile still cannot be used to infer conversion.

---

## 7. Dimensional model

### 7.1 SCD Type 2 still has no real history — LIMITATION
`dim_company` holds **38 rows, 38 companies, all `is_current`**. The scale-out briefly produced
5 versions, but they came from cosmetic renames ("AstraZeneca PLC" vs "plc"), so `legal_name` was
dropped from the tracked columns and the snapshot reset. The machinery is verified by simulation;
no genuine classification change has yet been captured. Structurally SCD2, operationally SCD1.

### 7.2 `dim_date` has no fiscal columns — LIMITATION (deliberate)
§9 lists `fiscal_quarter` and `fiscal_year` on `dim_date`. They are intentionally absent: five of
nine companies close off-calendar, so a single shared fiscal column would be wrong for most of
them. Fiscal periods live on the fact instead. This is a documented deviation, not an oversight —
but anything expecting §9's column list will not find them.

### 7.3 Taiwan macro gap was never solved, only avoided — LIMITATION
TSM was dropped from the universe partly because Taiwan has no World Bank coverage and TWD is
absent from Frankfurter. IMF was found to cover TWN for CPI but **not** GDP growth. The
underlying gap is unresolved; the universe was changed to route around it.

---

## 8. Pipeline and operations

### 8.1 DuckDB allows a single writer — LIMITATION
A running Streamlit dashboard holds a lock that **blocks the pipeline from writing** (observed:
`Could not set lock … Conflicting lock is held`). The dashboard must be stopped before a local
rebuild. Pointing the dashboard at Neon avoids it, but the local path retains the conflict.

### 8.2 Every run is a full rebuild — RISK
No incremental models anywhere. `raw.sec_edgar_facts` (172,673 rows) is dropped and rewritten on
every load, and pushed **over the network to Neon in full** each time. Acceptable at this size;
it does not scale to the Phase-8 universe.

### 8.3 Docker has never been tested — INCOMPLETE
Docker is not installed on the build machine. `docker-compose.yml` and the `Dockerfile` are
written and configured (Postgres, Dagster orchestrator, Metabase) but **have never been built or
run**. The claim that `docker compose up` works is unverified.

### 8.4 The Dagster schedule has never fired — INCOMPLETE
The 06:00 daily schedule ships `DefaultScheduleStatus.STOPPED` so importing the module cannot
silently start a cron. It has been executed manually end-to-end, but no scheduled run has ever
occurred, and the daemon has not been left running.

### 8.5 CI cannot test the hosted path — LIMITATION
CI builds against DuckDB with committed fixtures. It has no Neon credentials, so the Postgres
target, the network load path, and any Postgres-specific SQL behaviour are **never exercised in
CI** — only locally, by hand.

### 8.6 dbt runs as one monolithic step under Dagster — LIMITATION
`kubera_dbt_assets` shells out to `dbt build` for the entire project. Dagster shows the models as
individual assets, but they cannot be materialised selectively — re-running one mart rebuilds
everything.

### 8.7 Metabase was never set up — INCOMPLETE
§7 allows Metabase *or* Streamlit; Streamlit was built. The Metabase service is declared in
compose and never configured, so `dashboards/metabase_setup/` does not exist.

---

## 9. Dashboard

### 9.1 Drawdown and volatility charts are not built — INCOMPLETE
The Market Performance tab renders cumulative return only. Annualised volatility and max drawdown
are computable from the data (and were verified in SQL) but have no UI.

### 9.2 Light mode is validated but unreachable — LIMITATION
Both palettes passed the validator, but the app pins dark in `.streamlit/config.toml` and
`theme.py` selects on an env var that nothing sets. The light palette is dead code in practice,
and its three sub-3:1 slots have never been rendered.

### 9.3 No user-facing freshness indicator — LIMITATION
The sidebar shows row counts but not *when* data was last loaded. `world_bank_macro` carries a
`loaded_at` stamp specifically for revision auditing; nothing surfaces it.

---

## 10. Testing

### 10.1 The orchestration layer is untested — INCOMPLETE
83 pytest tests cover ingestion, the loader, config and the dashboard. **Zero** cover
`orchestration/dagster_pipeline.py` — no test asserts the asset graph, the source-to-asset
mapping, the retry policy or the sensor.

### 10.2 dbt unit tests cover three cases — LIMITATION
Only FX division, USD identity, and return partitioning. The dedup/restatement logic, the YTD
partial exclusion, the fiscal-year derivation and the FX forward-fill have **no unit tests** —
they are covered only indirectly by CI fixtures.

### 10.3 No test asserts warehouse parity between targets — INCOMPLETE
DuckDB and Neon are both built from the same models, but nothing verifies they produce identical
row counts or values. A dialect divergence would go unnoticed.

---

## 11. Repository and documentation

### 11.1 Phases 8 and 9 are not started — INCOMPLETE
**67 roadmap items remain open**: Phase 8 scale-out (17) and Phase 9 polish (15), plus scattered
earlier items. The universe is still the 9-company proving subset, not the ~40-name target in §6.

### 11.2 No architecture diagram — INCOMPLETE
`docs/architecture_diagram.md` is a placeholder. §8 and the Phase-9 checklist call for a real
`architecture_diagram.png`; the README has an ASCII sketch only.

### 11.3 The specification is duplicated — RISK
`kuber_edw_business_review.md` (root) and `docs/project_spec.md` are byte-identical copies. They
can drift independently and nothing enforces agreement.

### 11.4 TODO.md is 156 KB — LIMITATION
Roughly a third of the tracked repository by size, because every task carries its full
verification detail inline.

### 11.5 Dead configuration in .env.example — LIMITATION
`METALS_API_KEY` is documented and unused (§2.4). `PRICES_BACKEND` still offers `stooq`, which is
bot-gated and cannot succeed.

---

## 12. Scope boundaries (stated, not defects)

These are deliberate and disclosed in §11/§13, listed so they are not mistaken for bugs:

- Kubera is fictional; holdings are simulated. No claim of real ownership.
- The project models **public disclosed data only** — no private/operational data, no
  invoice-level transactions, no management accounts.
- Foreign private issuers file annually (20-F); quarterly cadence is genuinely uneven across the
  universe and is modelled, not corrected.
- Macro figures are revised after publication; `loaded_at` records which vintage was loaded.
- No investment advice, valuation opinion, or trading recommendation is expressed or implied.
