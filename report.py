#!/usr/bin/env python3
"""Utility script to fetch Freqtrade REST data and send Telegram updates."""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from requests import RequestException
from urllib3.util.retry import Retry

# API configuration (override via environment variables for container use).
API_BASE_URL = os.getenv("FREQTRADE_API_URL", "http://localhost:8080/api/v1")
API_USERNAME = os.getenv("FREQTRADE_API_USERNAME", "YOUR_USERNAME")
API_PASSWORD = os.getenv("FREQTRADE_API_PASSWORD", "YOUR_PASSWORD")

# Telegram settings (replace placeholders or export as environment variables).
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID")

# Report cadence (seconds). Default is 30 minutes.
REPORT_INTERVAL = int(os.getenv("REPORT_INTERVAL_SECONDS", "1800"))
TIMEOUT_SECONDS = int(os.getenv("REPORT_HTTP_TIMEOUT", "15"))

# HTTP retry configuration
HTTP_MAX_RETRIES = int(os.getenv("REPORT_HTTP_MAX_RETRIES", "3"))
HTTP_BACKOFF = float(os.getenv("REPORT_HTTP_BACKOFF", "1"))

# Telegram options
TELEGRAM_SILENT = (
    os.getenv("TELEGRAM_SILENT")
    or os.getenv("TELEGRAM_DISABLE_NOTIFICATION")
    or "false"
).strip().lower() in {"1", "true", "yes", "on"}

# Retry/backoff for startup / transient failures
RETRY_DELAY_SECONDS = int(os.getenv("REPORT_RETRY_DELAY_SECONDS", "10"))
ONCE_MAX_ATTEMPTS = int(os.getenv("REPORT_ONCE_MAX_ATTEMPTS", "6"))


def _build_retry() -> Retry:
    return Retry(
        total=HTTP_MAX_RETRIES,
        connect=HTTP_MAX_RETRIES,
        read=HTTP_MAX_RETRIES,
        status=HTTP_MAX_RETRIES,
        backoff_factor=HTTP_BACKOFF,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )


def init_session() -> requests.Session:
    """Create a requests session with auth and retry adapters."""
    session = requests.Session()
    session.auth = HTTPBasicAuth(API_USERNAME, API_PASSWORD)
    adapter = HTTPAdapter(max_retries=_build_retry())
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def fetch_endpoint(session: requests.Session, endpoint: str) -> dict:
    """GET a JSON payload from the specified REST endpoint."""
    url = f"{API_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    response = session.get(url, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def extract_status(status_payload: dict) -> tuple[str, str]:
    """Extract bot status text and open trade count if available."""
    if not isinstance(status_payload, dict):
        return str(status_payload), "n/a"

    state = status_payload.get("status") or status_payload.get("state") or "unknown"
    open_trades = status_payload.get("open_trades")
    if isinstance(open_trades, list):
        open_trades = len(open_trades)
    if open_trades is None:
        open_trades = status_payload.get("trades", "n/a")
    return str(state), str(open_trades)


def extract_profit(profit_payload: dict) -> tuple[str, str]:
    """Extract absolute and percentage profit details with graceful fallback."""
    if not isinstance(profit_payload, dict):
        return str(profit_payload), "n/a"

    abs_profit = (
        profit_payload.get("profit_total")
        or profit_payload.get("profit_sum")
        or profit_payload.get("profit_abs")
        or 0
    )
    pct_profit = (
        profit_payload.get("profit_pct")
        or profit_payload.get("profit_percent")
        or profit_payload.get("profit_ratio")
    )

    abs_string = f"{abs_profit:.8f}" if isinstance(abs_profit, (int, float)) else str(abs_profit)
    pct_string = (
        f"{pct_profit * 100:.2f}%" if isinstance(pct_profit, (int, float)) else str(pct_profit or "n/a")
    )
    return abs_string, pct_string


def extract_balance(balance_payload: dict) -> str:
    """Craft a concise balance summary from available fields."""
    if not isinstance(balance_payload, dict):
        return str(balance_payload)

    balance_section = (
        balance_payload.get("wallets")
        or balance_payload.get("balance")
        or balance_payload.get("total")
        or balance_payload
    )

    if isinstance(balance_section, dict):
        parts = []
        for currency, data in balance_section.items():
            if isinstance(data, dict):
                total = data.get("total") or data.get("available") or data.get("free")
                parts.append(f"{currency}: {total}")
            else:
                parts.append(f"{currency}: {data}")
        if parts:
            return ", ".join(parts[:5])

    return json.dumps(balance_section, default=str)[:200]


def build_message(status: str, trades: str, profit_abs: str, profit_pct: str, balance: str, pairlist_block: str | None = None) -> str:
    """Structure the Telegram message body."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = (
        "Freqtrade Status Report\n"
        f"Time: {timestamp}\n"
        f"Status: {status}\n"
        f"Open trades: {trades}\n"
        f"Profit: {profit_abs} ({profit_pct})\n"
        f"Balance: {balance}\n"
    )
    if pairlist_block:
        msg += f"\n{pairlist_block}\n"
    return msg


def fetch_whitelist(session: requests.Session) -> list[str]:
    """Fetch current whitelist/pairlist via REST. Returns a list of pairs."""
    endpoints = ("whitelist", "pairlist", "pairs")
    data = None
    for ep in endpoints:
        try:
            data = fetch_endpoint(session, ep)
            break
        except Exception:
            continue
    if data is None:
        return []
    if isinstance(data, dict):
        for key in ("whitelist", "pairs", "pairlist"):
            if key in data and isinstance(data[key], list):
                return [str(x) for x in data[key]]
        # Some implementations return raw list in dict
        try:
            return [str(x) for x in data.values()][0]  # type: ignore[index]
        except Exception:
            return []
    if isinstance(data, list):
        return [str(x) for x in data]
    return []


def format_pairlist(pairs: list[str]) -> str:
    """Return a clean, human-friendly pairlist block for Telegram."""
    if not pairs:
        return ""
    limit = int(os.getenv("REPORT_PAIRLIST_LIMIT", "25"))
    style = (os.getenv("REPORT_PAIRLIST_STYLE", "list") or "list").strip().lower()
    heading = os.getenv("REPORT_PAIRLIST_HEADING", "Pairlist")
    shown = pairs[:limit]

    if style == "columns":
        cols = max(1, int(os.getenv("REPORT_PAIRLIST_COLUMNS", "3")))
        colwidth = max(8, int(os.getenv("REPORT_PAIRLIST_COLWIDTH", "18")))
        # Build rows
        rows: list[list[str]] = []
        row: list[str] = []
        for i, p in enumerate(shown, 1):
            label = f"{i:2d}. {p}"
            row.append(label.ljust(colwidth))
            if len(row) == cols:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        body = "\n".join("".join(r) for r in rows)
        return f"{heading} ({len(pairs)} total, showing {len(shown)}):\n```\n{body}\n```"

    # Default: numbered list, one per line
    lines = [f"{heading} ({len(pairs)} total, showing {len(shown)}):"]
    lines.extend(f"{i:2d}. {p}" for i, p in enumerate(shown, 1))
    return "\n".join(lines)


def send_telegram_message(session: requests.Session, message: str) -> None:
    """POST a markdown-formatted message to Telegram."""
    if "YOUR_TELEGRAM_BOT_TOKEN" in TELEGRAM_TOKEN:
        raise RuntimeError("Telegram token placeholder detected. Configure Telegram credentials before running.")
    if "YOUR_TELEGRAM_CHAT_ID" in TELEGRAM_CHAT_ID:
        raise RuntimeError("Telegram chat_id placeholder detected. Configure Telegram credentials before running.")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_notification": TELEGRAM_SILENT,
    }
    response = session.post(url, json=payload, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()


def run_report(session: requests.Session) -> None:
    """Fetch REST resources, compose the message, and push to Telegram."""
    status_payload = fetch_endpoint(session, "status")
    profit_payload = fetch_endpoint(session, "profit")
    balance_payload = fetch_endpoint(session, "balance")

    status, trades = extract_status(status_payload)
    profit_abs, profit_pct = extract_profit(profit_payload)
    balance_info = extract_balance(balance_payload)

    pairlist_block = None
    if (os.getenv("REPORT_INCLUDE_PAIRLIST") or "false").strip().lower() in {"1", "true", "yes", "on"}:
        pairs = fetch_whitelist(session)
        pairlist_block = format_pairlist(pairs) if pairs else None

    message = build_message(status, trades, profit_abs, profit_pct, balance_info, pairlist_block)
    send_telegram_message(session, message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send periodic Freqtrade status reports to Telegram.")
    parser.add_argument("--once", action="store_true", help="Run a single report cycle and exit (for cron usage).")
    args = parser.parse_args()

    if "YOUR_USERNAME" in API_USERNAME or "YOUR_PASSWORD" in API_PASSWORD:
        print("[ERROR] API credentials placeholders detected. Configure Freqtrade REST auth first.", file=sys.stderr)
        return 1

    session = init_session()

    try:
        attempts = 0
        while True:
            try:
                run_report(session)
                if args.once:
                    break
                time.sleep(REPORT_INTERVAL)
            except RequestException as exc:
                attempts += 1
                print(f"[WARN] Request error: {exc}", file=sys.stderr)
                if args.once and attempts >= ONCE_MAX_ATTEMPTS:
                    print("[ERROR] Exceeded max attempts for --once run.", file=sys.stderr)
                    return 1
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            except Exception as exc:  # pylint: disable=broad-except
                attempts += 1
                print(f"[WARN] Unexpected error: {exc}", file=sys.stderr)
                if args.once and attempts >= ONCE_MAX_ATTEMPTS:
                    print("[ERROR] Exceeded max attempts for --once run.", file=sys.stderr)
                    return 1
                time.sleep(RETRY_DELAY_SECONDS)
                continue
    finally:
        session.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())

# Docker usage notes:
#   Place this script inside ./user_data/scripts and ensure execution permission:
#     chmod +x user_data/scripts/report.py
#   Run inside the freqtrade container with required environment variables:
#     docker compose run --rm freqtrade \
#       -v $(pwd)/user_data/scripts/report.py:/freqtrade/user_data/scripts/report.py \
#       -e FREQTRADE_API_USERNAME=YOUR_USERNAME \
#       -e FREQTRADE_API_PASSWORD=YOUR_PASSWORD \
#       -e TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN \
#       -e TELEGRAM_CHAT_ID=YOUR_TELEGRAM_CHAT_ID \
#       freqtradeorg/freqtrade:develop \
#       /freqtrade/user_data/scripts/report.py
#
# Cron scheduling example (inside the container):
#   */30 * * * * /freqtrade/user_data/scripts/report.py --once \
#     >> /freqtrade/user_data/logs/report.log 2>&1
