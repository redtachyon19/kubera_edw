"""JSON endpoint behind the Stock Explorer.

The Stock Explorer is a native page in the hub, not an embedded dashboard, so it
needs data over HTTP rather than a Streamlit process. This is a stdlib server —
no web framework, nothing added to `requirements.txt` beyond `yfinance` — that
the Vite dev server proxies `/api/market/*` to.

It exists because Yahoo's JSON hosts reject requests without a session cookie and
crumb; `yfinance` handles that handshake, so the browser talks to this instead of
to Yahoo directly.

    GET /api/market/search?q=apple
    GET /api/market/history?symbols=AAPL,MSFT,GC=F&period=5Y
    GET /api/market/quotes?symbols=^GSPC,GC=F
    GET /api/market/sectors?period=1Y
    GET /api/market/sector?slug=ai&period=1Y
    GET /api/market/companies?period=1Y
    GET /api/market/company?symbol=AAPL
    GET /api/market/revenue?symbol=AAPL
    GET /api/market/news?slug=ai
    GET /api/market/news?symbol=AAPL
    GET /api/market/world?period=1Y
    GET /api/market/world-sectors?period=1Y
    GET /api/market/world-energy?period=1Y
    GET /api/market/world-country?iso3=JPN&period=5Y
    GET /api/market/world-trade?iso3=JPN
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# The same `.env` the pipeline reads. Without this the server starts with an
# empty environment and every SEC lookup silently degrades to the quote feed —
# a page of four annual periods where the filings hold seventy quarters, with
# nothing on screen to say why.
try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:  # pragma: no cover — python-dotenv ships with the project
    pass

from dashboard_hub.lib import filings, market_data, trade, world  # noqa: E402

PORT = 8600


class Handler(BaseHTTPRequestHandler):
    """Two read-only endpoints. Bound to localhost by the server below."""

    def _send(self, payload: dict | list, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's naming
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        try:
            if parsed.path == "/api/market/search":
                query = (params.get("q") or [""])[0]
                self._send({"results": market_data.search(query)})
                return

            if parsed.path == "/api/market/history":
                raw = (params.get("symbols") or [""])[0]
                symbols = [s.strip() for s in raw.split(",") if s.strip()]
                period = (params.get("period") or ["5Y"])[0]
                self._send(market_data.history(symbols, period))
                return

            if parsed.path == "/api/market/sectors":
                period = (params.get("period") or ["1Y"])[0]
                self._send({"sectors": market_data.sectors_overview(period)})
                return

            if parsed.path == "/api/market/sector":
                slug = (params.get("slug") or [""])[0]
                definition = market_data.sector(slug)
                if not definition:
                    self._send({"error": f"unknown sector {slug!r}"}, status=404)
                    return
                period = (params.get("period") or ["1Y"])[0]
                snapshot = market_data.sector_snapshot(definition["symbols"], period)
                self._send({**definition, **snapshot})
                return

            if parsed.path == "/api/market/companies":
                period = (params.get("period") or ["1Y"])[0]
                self._send({"companies": market_data.companies_overview(period)})
                return

            if parsed.path == "/api/market/world":
                period = (params.get("period") or ["1Y"])[0]
                self._send(world.snapshot(period))
                return

            if parsed.path == "/api/market/world-sectors":
                period = (params.get("period") or ["1Y"])[0]
                self._send(world.sectors(period))
                return

            if parsed.path == "/api/market/world-energy":
                period = (params.get("period") or ["1Y"])[0]
                self._send(world.energy(period))
                return

            if parsed.path == "/api/market/world-country":
                iso3 = (params.get("iso3") or [""])[0]
                if len(iso3) != 3:
                    self._send({"error": "a three-letter country code is required"}, status=400)
                    return
                period = (params.get("period") or ["5Y"])[0]
                self._send(world.country(iso3, period))
                return

            if parsed.path == "/api/market/world-trade":
                iso3 = (params.get("iso3") or [""])[0]
                if len(iso3) != 3:
                    self._send({"error": "a three-letter country code is required"}, status=400)
                    return
                self._send(
                    {
                        **trade.partners(iso3),
                        "composition": trade.composition(iso3),
                    }
                )
                return

            if parsed.path == "/api/market/revenue":
                symbol = (params.get("symbol") or [""])[0]
                self._send(market_data.revenue_history(symbol))
                return

            if parsed.path == "/api/market/company":
                symbol = (params.get("symbol") or [""])[0]
                payload = market_data.company(symbol)
                if not payload:
                    self._send({"error": "no symbol given"}, status=400)
                    return
                self._send(payload)
                return

            if parsed.path == "/api/market/news":
                # One feed, two callers: a sector takes the union across its
                # largest names, a company just its own.
                symbol = (params.get("symbol") or [""])[0]
                if symbol:
                    self._send({"stories": market_data.company_news(symbol)})
                    return
                slug = (params.get("slug") or [""])[0]
                self._send({"stories": market_data.sector_news(slug)})
                return

            if parsed.path == "/api/market/quotes":
                raw = (params.get("symbols") or [""])[0]
                wanted = tuple(s.strip() for s in raw.split(",") if s.strip())
                self._send({"quotes": market_data.quotes(wanted)})
                return

            if parsed.path == "/api/market/backfill":
                symbol = (params.get("symbol") or [""])[0]
                self._send(market_data.backfill_status(symbol))
                return

            if parsed.path == "/api/market/health":
                self._send(
                    {
                        "ok": True,
                        "periods": list(market_data.PERIODS),
                        "edgar": filings.available(),
                    }
                )
                return

            self._send({"error": f"no route for {parsed.path}"}, status=404)
        except Exception as exc:  # noqa: BLE001 — never take the page down on a data error
            print(f"[market-api] {parsed.path}: {exc!r}", file=sys.stderr)
            self._send({"error": str(exc)}, status=502)

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's naming
        """The one endpoint that changes anything: queue a company for the warehouse.

        A POST rather than a GET because it is a request to do work, and because
        a GET that mutates gets fetched by every prefetcher and link checker
        that ever sees the page.
        """
        parsed = urlparse(self.path)
        if parsed.path != "/api/market/backfill":
            self._send({"error": f"no route for POST {parsed.path}"}, status=404)
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            symbol = str(body.get("symbol") or "").strip()
            if not symbol:
                self._send({"error": "a symbol is required"}, status=400)
                return
            self._send(market_data.request_backfill(symbol), status=202)
        except json.JSONDecodeError:
            self._send({"error": "body must be JSON"}, status=400)
        except Exception as exc:  # noqa: BLE001 — never take the page down on a data error
            print(f"[market-api] POST {parsed.path}: {exc!r}", file=sys.stderr)
            self._send({"error": str(exc)}, status=502)

    def log_message(self, fmt: str, *args) -> None:
        """Quieter than the default: one line per request, on stderr."""
        sys.stderr.write(f"[market-api] {fmt % args}\n")


WORKER_INTERVAL = 5


def _backfill_worker() -> None:
    """Run whatever the desk has queued, without anyone opening a terminal.

    Dagster owns this job when its daemon is up, and that is the better home for
    it — retries, run history, a UI. But the hub runs on its own far more often
    than the daemon does, and a button that only writes a request to a file and
    tells you to go and run something is not a button. So the API drains the
    queue itself.

    Both workers claim a request before starting, so whichever gets there first
    does the work once. Set `KUBERA_BACKFILL_WORKER=0` to leave it all to
    Dagster.
    """
    try:
        from ingestion import backfill
    except ImportError as exc:  # a checkout without the extractor stack installed
        print(f"[market-api] backfill worker off: {exc}", file=sys.stderr)
        return

    while True:
        try:
            for row in backfill.pending():
                ticker = row["ticker"]
                if not backfill.claim(ticker):
                    continue
                print(f"[market-api] backfilling {ticker} — this takes a few minutes")
                finished = backfill.run(ticker)
                status = finished.get("status")
                if status == backfill.FAILED:
                    print(f"[market-api] {ticker} failed: {finished.get('error')}", file=sys.stderr)
                else:
                    print(f"[market-api] {ticker} is now a holding")
        except Exception as exc:  # noqa: BLE001 — the worker must outlive one bad request
            print(f"[market-api] backfill worker error: {exc!r}", file=sys.stderr)
        time.sleep(WORKER_INTERVAL)


def _warm_trade() -> None:
    """Fill the trade-composition cache in the background, quietly."""
    try:
        countries = len(trade.composition_world())
        if countries:
            print(f"[market-api] trade composition ready — {countries} countries")
    except Exception as exc:  # noqa: BLE001 — a cold cache is a slow panel, not a failure
        print(f"[market-api] trade composition warm-up failed: {exc!r}", file=sys.stderr)


def serve(port: int = PORT) -> None:
    server = ThreadingHTTPServer(("localhost", port), Handler)
    print(f"[market-api] listening on http://localhost:{port}")

    if os.environ.get("KUBERA_BACKFILL_WORKER", "1") != "0":
        threading.Thread(target=_backfill_worker, daemon=True, name="backfill").start()
        print("[market-api] backfill worker running — queued companies build here")

    # The world's trade composition is ten World Bank walks — about a minute,
    # once a week. Doing it here means the first reader to open a country gets it
    # from the cache instead of waiting for it.
    threading.Thread(target=_warm_trade, daemon=True, name="trade-warm").start()
    # Say which sources are actually available, because the difference between
    # them is twenty years of history and it is otherwise invisible.
    if filings.available():
        print("[market-api] SEC EDGAR enabled — full filing history")
    else:
        print(
            "[market-api] SEC_EDGAR_USER_AGENT is not set: revenue history falls back to "
            'Yahoo (4 years). Add it to .env as "Name you@example.com" for the full run.',
            file=sys.stderr,
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
