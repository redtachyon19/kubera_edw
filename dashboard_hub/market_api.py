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
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard_hub.lib import market_data  # noqa: E402

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

            if parsed.path == "/api/market/quotes":
                raw = (params.get("symbols") or [""])[0]
                wanted = tuple(s.strip() for s in raw.split(",") if s.strip())
                self._send({"quotes": market_data.quotes(wanted)})
                return

            if parsed.path == "/api/market/health":
                self._send({"ok": True, "periods": list(market_data.PERIODS)})
                return

            self._send({"error": f"no route for {parsed.path}"}, status=404)
        except Exception as exc:  # noqa: BLE001 — never take the page down on a data error
            print(f"[market-api] {parsed.path}: {exc!r}", file=sys.stderr)
            self._send({"error": str(exc)}, status=502)

    def log_message(self, fmt: str, *args) -> None:
        """Quieter than the default: one line per request, on stderr."""
        sys.stderr.write(f"[market-api] {fmt % args}\n")


def serve(port: int = PORT) -> None:
    server = ThreadingHTTPServer(("localhost", port), Handler)
    print(f"[market-api] listening on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
