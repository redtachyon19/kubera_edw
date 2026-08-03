"""Run every Kubera dashboard as its own Streamlit process for the hub.

Hub and spoke: the hub is the Vite app in `dashboard_hub/hub` (port 5173);
each dashboard is an independent Streamlit server on its own port, served under the
same `--server.baseUrlPath` the Vite dev proxy routes to. The hub embeds each one
in an iframe, so a dashboard can be restarted, rewritten or replaced with a different
framework entirely without touching the hub.

    make hub                       # both halves, one command
    make hub-dashboards            # just the Streamlit processes
    .venv/bin/python dashboard_hub/run_local.py

Ctrl+C stops every dashboard.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registry  # noqa: E402


def _theme_env() -> dict[str, str]:
    """Translate the registry's `theme.streamlit` block into `STREAMLIT_THEME_*` variables.

    Dashboards run with their own directory as the working directory, so they never
    pick up a `.streamlit/config.toml` on their own. Passing the theme down as
    environment keeps the hub and its dashboards on one palette without a config copy
    per dashboard — and leaves the standalone 8501 app's own theme alone.
    """
    block = registry.theme().get("streamlit", {})
    env: dict[str, str] = {}
    for key, value in block.items():
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", key).upper()
        env[f"STREAMLIT_THEME_{snake}"] = str(value)
    return env


def _preflight() -> None:
    """Fail early with a clear message if Streamlit is not on this interpreter."""
    try:
        import streamlit  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Streamlit is not installed in this interpreter. Launch with the project venv:\n"
            "  .venv/bin/python dashboard_hub/run_local.py\n"
            "(or run `make setup` first)"
        ) from exc


def _launch(
    script: Path, port: int, base_url_path: str, cwd: Path, extra_env: dict[str, str]
) -> subprocess.Popen:
    """Start a headless Streamlit process under a base URL path.

    The base path matches what the Vite dev proxy forwards, so a dashboard behaves the
    same whether it is opened through the hub or hit directly on its own port.
    Anything the caller's shell already exports wins over `extra_env`, so a
    developer can override the theme or `DUCKDB_PATH` for a single run.
    """
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(script),
        "--server.port",
        str(port),
        "--server.address",
        "localhost",
        "--server.baseUrlPath",
        base_url_path,
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    child_env = os.environ.copy()
    for key, value in extra_env.items():
        child_env.setdefault(key, value)
    return subprocess.Popen(cmd, cwd=str(cwd), env=child_env)


def _print_banner(entries: list[dict]) -> None:
    bar = "=" * 78
    print("\n" + bar)
    print("Kubera dashboards started. Open the hub:  http://localhost:5173")
    print("  (if you started this script on its own, run the hub in a second terminal:")
    print("   cd dashboard_hub/hub && npm install && npm run dev)")
    print("-" * 78)
    for entry in entries:
        path = registry.base_path(str(entry["id"]))
        print(f"  {str(entry['title'])[:32]:<32} http://localhost:{entry['port']}{path}")
    planned = [e for e in registry.dashboards() if e.get("status") != "stub"]
    if planned:
        names = ", ".join(str(e["title"]) for e in planned)
        print("-" * 78)
        print(f"  Not yet wired up (hub shows a placeholder card): {names}")
    print(bar)
    print("Press Ctrl+C to stop.\n")


def _shutdown(procs: list[tuple[str, subprocess.Popen]]) -> None:
    """Terminate every child, hard-killing any that ignores terminate."""
    for _, proc in procs:
        if proc.poll() is None:
            proc.terminate()
    deadline = time.monotonic() + 5.0
    for _, proc in procs:
        try:
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    """Launch every servable dashboard, then block until interrupted.

    Returns:
        0 on clean shutdown (Ctrl+C), 1 if every dashboard exited on its own —
        typically a port already in use.
    """
    _preflight()
    entries = registry.servable()
    if not entries:
        print("[error] no dashboards with status 'stub' in dashboards.json", file=sys.stderr)
        return 1

    theme_env = _theme_env()
    procs: list[tuple[str, subprocess.Popen]] = []
    warned: set[str] = set()
    try:
        # The market API backs the hub's own native pages — not a dashboard
        # process, but it has to be up for them to have anything to draw.
        procs.append(
            (
                "Market API",
                subprocess.Popen(
                    [sys.executable, "-u", str(registry.ROOT_DIR / "market_api.py")],
                    cwd=str(registry.ROOT_DIR),
                    env=os.environ.copy(),
                ),
            )
        )

        for entry in entries:
            app_dir = registry.dashboard_dir(entry)
            app_py = app_dir / "app.py"
            if not app_py.exists():
                raise FileNotFoundError(
                    f"Dashboard '{entry['id']}' is marked servable but {app_py} is missing."
                )
            procs.append(
                (
                    str(entry["title"]),
                    _launch(
                        app_py,
                        int(entry["port"]),
                        registry.base_path(str(entry["id"])),
                        app_dir,
                        # Widgets inside a dashboard pick up its own section's metal,
                        # so the frame and its contents match.
                        {**theme_env, "STREAMLIT_THEME_PRIMARY_COLOR": str(entry["accent"])},
                    ),
                )
            )

        _print_banner(entries)

        while True:
            time.sleep(1.0)
            for label, proc in procs:
                code = proc.poll()
                if code is not None and label not in warned:
                    warned.add(label)
                    print(f"[warn] dashboard exited: {label} (code {code})", file=sys.stderr)
            if all(proc.poll() is not None for _, proc in procs):
                print("[error] every dashboard exited; shutting down.", file=sys.stderr)
                return 1
    except KeyboardInterrupt:
        print("\nStopping the dashboards…")
        return 0
    finally:
        _shutdown(procs)


if __name__ == "__main__":
    raise SystemExit(main())
