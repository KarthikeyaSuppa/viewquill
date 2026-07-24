"""
Runs `npx ccusage@latest daily --json`, merges the result into a local
history file, and regenerates a human-readable Markdown log.

Usage:
    python scripts/ccusage_daily_log.py

Intended to be run once per day (e.g. via Windows Task Scheduler). Safe to
run multiple times per day too -- each day's row is upserted, not appended,
so re-running just refreshes today's numbers.

Output (created next to this script's repo root, under ccusage-log/):
    ccusage-log/history.json   -- raw per-day data, source of truth
    ccusage-log/CCUSAGE-LOG.md -- formatted table for humans

Markdown was chosen over Excel/Word because it needs no extra pip
dependencies (openpyxl / python-docx), renders as a table in VS Code/GitHub,
and diffs cleanly in git.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "ccusage-log"
HISTORY_PATH = LOG_DIR / "history.json"
MARKDOWN_PATH = LOG_DIR / "CCUSAGE-LOG.md"


def run_ccusage() -> dict:
    cmd = "npx ccusage@latest daily --json"
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        sys.exit(
            f"ccusage failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        sys.exit(f"Could not parse ccusage output as JSON: {exc}\n{result.stdout[:500]}")


def load_history() -> dict:
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    return {}


def merge_history(history: dict, payload: dict) -> dict:
    for day in payload.get("daily", []):
        date = day.get("date") or day.get("period")
        if date is None:
            continue
        history[date] = day
    return history


def save_history(history: dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, indent=2, sort_keys=True), encoding="utf-8"
    )


def fmt_cost(value: float) -> str:
    return f"${value:,.2f}"


def fmt_tokens(value: int) -> str:
    return f"{value:,}"


def render_markdown(history: dict) -> str:
    dates = sorted(history.keys(), reverse=True)
    lines = [
        "# ccusage daily log",
        "",
        f"Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "| Date | Input | Output | Cache Create | Cache Read | Total Tokens | Cost | Models |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]

    total_cost = 0.0
    total_tokens = 0
    for date in dates:
        day = history[date]
        total_cost += day.get("totalCost", 0)
        total_tokens += day.get("totalTokens", 0)
        models = ", ".join(m.split("-")[1] if "-" in m else m for m in day.get("modelsUsed", []))
        lines.append(
            "| {date} | {inp} | {out} | {cc} | {cr} | {tot} | {cost} | {models} |".format(
                date=date,
                inp=fmt_tokens(day.get("inputTokens", 0)),
                out=fmt_tokens(day.get("outputTokens", 0)),
                cc=fmt_tokens(day.get("cacheCreationTokens", 0)),
                cr=fmt_tokens(day.get("cacheReadTokens", 0)),
                tot=fmt_tokens(day.get("totalTokens", 0)),
                cost=fmt_cost(day.get("totalCost", 0)),
                models=models,
            )
        )

    lines += [
        "",
        f"**Running total ({len(dates)} day{'s' if len(dates) != 1 else ''} logged):** "
        f"{fmt_tokens(total_tokens)} tokens, {fmt_cost(total_cost)}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    payload = run_ccusage()
    history = load_history()
    history = merge_history(history, payload)
    save_history(history)
    MARKDOWN_PATH.write_text(render_markdown(history), encoding="utf-8")
    print(f"Logged {len(payload.get('daily', []))} day(s). See {MARKDOWN_PATH}")


if __name__ == "__main__":
    main()
