"""
Pulls the full ccusage picture -- sessions, daily, weekly, monthly, billing
blocks, and grand totals -- merges it into a local history file, and
regenerates a rich, human-readable Markdown log.

Usage:
    python scripts/ccusage_daily_log.py

Intended to run once per day (e.g. Windows Task Scheduler), but safe to run
any number of times. Every row is *upserted* by its natural key -- date /
week-start / month / session-id / block-id -- never blindly appended, so
re-running just refreshes the latest numbers.

Why keep our own history at all? ccusage reads Claude Code's local JSONL logs,
which get pruned over time. By upserting every run into history.json we retain
the complete record even after ccusage itself forgets old days/sessions.

Data is fetched in just two ccusage calls:
    npx ccusage@latest --sections daily,weekly,monthly,session --json
    npx ccusage@latest blocks --json

Output (under <repo>/ccusage-log/):
    history.json    -- raw, complete per-report data, the source of truth
    CCUSAGE-LOG.md  -- formatted multi-section report for humans

Markdown was chosen over Excel/Word because it needs no extra pip
dependencies, renders as tables in VS Code/GitHub, and diffs cleanly in git.
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

# Report groupings pulled in one unified --sections load. Each row is keyed in
# history.json by its own "period" value (a date / week-start / month / uuid).
SECTION_KEYS = ("daily", "weekly", "monthly", "session")
# Every top-level usage section we persist (the four above + billing blocks).
HISTORY_SECTIONS = SECTION_KEYS + ("blocks",)

# Token fields shared by every grouped row (and normalised block, see below).
TOKEN_FIELDS = (
    "inputTokens",
    "outputTokens",
    "cacheCreationTokens",
    "cacheReadTokens",
    "totalTokens",
)


# --------------------------------------------------------------------------- #
# Running ccusage
# --------------------------------------------------------------------------- #
def _run(cmd: str, *, fatal: bool = True):
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=REPO_ROOT
    )
    if result.returncode != 0:
        msg = f"`{cmd}` failed (exit {result.returncode}):\n{result.stderr.strip()}"
        if fatal:
            sys.exit(msg)
        print(f"WARNING: {msg}", file=sys.stderr)
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        msg = f"Could not parse JSON from `{cmd}`: {exc}\n{result.stdout[:500]}"
        if fatal:
            sys.exit(msg)
        print(f"WARNING: {msg}", file=sys.stderr)
        return None


def fetch_sections() -> dict:
    """daily + weekly + monthly + session + totals, in a single ccusage load."""
    return _run("npx ccusage@latest --sections daily,weekly,monthly,session --json")


def fetch_blocks() -> list:
    """5-hour billing blocks. Non-fatal -- this is bonus detail."""
    payload = _run("npx ccusage@latest blocks --json", fatal=False)
    return payload.get("blocks", []) if payload else []


# --------------------------------------------------------------------------- #
# History load / merge / save (upsert by natural key)
# --------------------------------------------------------------------------- #
def load_history() -> dict:
    if not HISTORY_PATH.exists():
        return {section: {} for section in HISTORY_SECTIONS}
    data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    # Legacy format was a flat {date: dayRow} dict of daily data only. Detect
    # it by the absence of any known section key and migrate it under "daily".
    if not any(section in data for section in HISTORY_SECTIONS):
        data = {"daily": data}
    for section in HISTORY_SECTIONS:
        data.setdefault(section, {})
    return data


def merge_sections(history: dict, payload: dict) -> None:
    for section in SECTION_KEYS:
        for row in payload.get(section, []):
            key = row.get("period")
            if key is not None:
                history[section][key] = row
    if isinstance(payload.get("totals"), dict):
        # Kept purely as a reference snapshot; grand totals below are computed
        # from our accumulated daily history so they never shrink.
        history["totals_snapshot"] = payload["totals"]


def merge_blocks(history: dict, blocks: list) -> None:
    for block in blocks:
        # Gap blocks are idle filler with no usage -- skip them.
        if block.get("isGap") or block.get("id") is None:
            continue
        history["blocks"][block["id"]] = block


def save_history(history: dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, indent=2, sort_keys=True), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def fmt_cost(value: float) -> str:
    return f"${value:,.2f}"


def fmt_tokens(value: int) -> str:
    return f"{value:,}"


def fmt_compact(value: float) -> str:
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(value) >= size:
            return f"{value / size:.2f}{unit}"
    return str(int(value))


def short_model(name: str) -> str:
    # "claude-opus-4-8" -> "opus", "claude-haiku-4-5-20251001" -> "haiku".
    parts = name.split("-")
    return parts[1] if len(parts) > 1 and parts[0] == "claude" else name


def models_label(row: dict) -> str:
    return ", ".join(short_model(m) for m in row.get("modelsUsed", []))


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def zero_bucket() -> dict:
    bucket = {field: 0 for field in TOKEN_FIELDS}
    bucket["totalCost"] = 0.0
    return bucket


def add_row(bucket: dict, row: dict) -> None:
    for field in TOKEN_FIELDS:
        bucket[field] += row.get(field, 0) or 0
    bucket["totalCost"] += row.get("totalCost", 0) or 0.0


def total_of(rows) -> dict:
    bucket = zero_bucket()
    for row in rows:
        add_row(bucket, row)
    return bucket


def aggregate_by_model(rows) -> dict:
    """Sum each model's usage across the given rows via their modelBreakdowns."""
    models: dict = {}
    for row in rows:
        for mb in row.get("modelBreakdowns", []):
            bucket = models.setdefault(mb.get("modelName", "unknown"), zero_bucket())
            for field in ("inputTokens", "outputTokens", "cacheCreationTokens", "cacheReadTokens"):
                bucket[field] += mb.get(field, 0) or 0
            # Breakdowns carry no totalTokens -- derive it from the four parts.
            bucket["totalTokens"] += sum(
                mb.get(f, 0) or 0
                for f in ("inputTokens", "outputTokens", "cacheCreationTokens", "cacheReadTokens")
            )
            bucket["totalCost"] += mb.get("cost", 0) or 0.0
    return models


def block_tokens(block: dict) -> dict:
    """Normalise a block's nested tokenCounts into the shared field names."""
    tc = block.get("tokenCounts", {})
    return {
        "inputTokens": tc.get("inputTokens", 0),
        "outputTokens": tc.get("outputTokens", 0),
        "cacheCreationTokens": tc.get("cacheCreationInputTokens", 0),
        "cacheReadTokens": tc.get("cacheReadInputTokens", 0),
        "totalTokens": block.get("totalTokens", 0),
        "totalCost": block.get("costUSD", 0),
    }


def session_last_activity(row: dict) -> str:
    return (row.get("metadata") or {}).get("lastActivity") or ""


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #
def token_cells(bucket: dict) -> str:
    """The six shared cells: input | output | cache-create | cache-read | total | cost."""
    return (
        f"{fmt_tokens(bucket.get('inputTokens', 0))} | "
        f"{fmt_tokens(bucket.get('outputTokens', 0))} | "
        f"{fmt_tokens(bucket.get('cacheCreationTokens', 0))} | "
        f"{fmt_tokens(bucket.get('cacheReadTokens', 0))} | "
        f"{fmt_tokens(bucket.get('totalTokens', 0))} | "
        f"{fmt_cost(bucket.get('totalCost', 0))}"
    )


def render_sessions_section(sessions: dict) -> list:
    keys = sorted(sessions, key=lambda k: session_last_activity(sessions[k]), reverse=True)
    n = len(keys)
    out = [
        "## Sessions",
        "",
        f"_{n} session{'' if n == 1 else 's'} recorded — one row per Claude Code session, newest activity first._",
        "",
        "| Session | Last Activity (UTC) | Input | Output | Cache Create | Cache Read | Total Tokens | Cost | Models |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key in keys:
        row = sessions[key]
        activity = session_last_activity(row).replace("T", " ")[:16] or "—"
        out.append(f"| `{key[:8]}` | {activity} | {token_cells(row)} | {models_label(row)} |")
    out.append(f"| **Total** | | {token_cells(total_of(sessions.values()))} | |")
    out.append("")
    return out


def render_period_section(title: str, rows: dict, label_header: str, noun: str) -> list:
    keys = sorted(rows, reverse=True)
    n = len(keys)
    out = [
        f"## {title}",
        "",
        f"_{n} {noun}{'' if n == 1 else 's'} recorded, newest first._",
        "",
        f"| {label_header} | Input | Output | Cache Create | Cache Read | Total Tokens | Cost | Models |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for key in keys:
        out.append(f"| {key} | {token_cells(rows[key])} | {models_label(rows[key])} |")
    out.append(f"| **Total** | {token_cells(total_of(rows.values()))} | |")
    out.append("")
    return out


def render_whole_usage(history: dict) -> list:
    daily = history["daily"]
    sessions = history["session"]
    grand = total_of(daily.values())  # daily is the complete, non-overlapping record
    dates = sorted(daily)
    n_days, n_sessions = len(dates), len(sessions)
    span = f"{dates[0]} → {dates[-1]}" if dates else "—"

    out = [
        "## Whole usage",
        "",
        "_Grand totals across every recorded day — the complete, non-overlapping picture._",
        "",
        f"- **Total cost:** {fmt_cost(grand['totalCost'])}",
        f"- **Total tokens:** {fmt_tokens(grand['totalTokens'])} ({fmt_compact(grand['totalTokens'])})",
        f"- **Output tokens (actually generated):** {fmt_tokens(grand['outputTokens'])}",
        f"- **Date range:** {span}  ·  {n_days} day{'' if n_days == 1 else 's'}, "
        f"{n_sessions} session{'' if n_sessions == 1 else 's'}",
        "",
        "| Scope | Input | Output | Cache Create | Cache Read | Total Tokens | Cost |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| All recorded usage | {token_cells(grand)} |",
        "",
    ]

    # Derived highlights.
    cost_of = lambda row: row.get("totalCost", 0) or 0
    top_day = max(daily.values(), key=cost_of, default=None)
    top_session = max(sessions.values(), key=cost_of, default=None)
    cache_ratio = (
        grand["cacheReadTokens"] / grand["totalTokens"] * 100 if grand["totalTokens"] else 0
    )
    out += ["### Highlights", ""]
    if n_days:
        out.append(f"- **Avg cost / day:** {fmt_cost(grand['totalCost'] / n_days)}")
    if n_sessions:
        out.append(f"- **Avg cost / session:** {fmt_cost(grand['totalCost'] / n_sessions)}")
    if top_day:
        out.append(
            f"- **Most expensive day:** {top_day.get('period')} — {fmt_cost(cost_of(top_day))}"
        )
    if top_session:
        activity = session_last_activity(top_session).replace("T", " ")[:16] or "n/a"
        out.append(
            f"- **Most expensive session:** `{str(top_session.get('period', ''))[:8]}` "
            f"({activity}) — {fmt_cost(cost_of(top_session))}"
        )
    out.append(f"- **Cache-read share of tokens:** {cache_ratio:.1f}% (higher = more prompt-cache reuse)")
    out.append("")

    # Per-model aggregate.
    out += [
        "### Usage by model",
        "",
        "_Aggregated from every day's per-model breakdown._",
        "",
        "| Model | Input | Output | Cache Create | Cache Read | Total Tokens | Cost | % Cost |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    models = aggregate_by_model(daily.values())
    for name, bucket in sorted(models.items(), key=lambda kv: kv[1]["totalCost"], reverse=True):
        pct = bucket["totalCost"] / grand["totalCost"] * 100 if grand["totalCost"] else 0
        out.append(f"| {name} | {token_cells(bucket)} | {pct:.1f}% |")
    out.append(f"| **Total** | {token_cells(grand)} | 100.0% |")
    out.append("")
    return out


def render_blocks_section(blocks: dict) -> list:
    keys = sorted(blocks, reverse=True)  # id is the ISO block-start time
    n = len(keys)
    out = [
        "## Billing blocks",
        "",
        f"_{n} usage block{'' if n == 1 else 's'} — Claude meters usage in rolling 5-hour "
        "windows; idle gaps are omitted._",
        "",
        "| Start (UTC) | Entries | Input | Output | Cache Create | Cache Read | Total Tokens | Cost | Models | Active |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|:--:|",
    ]
    agg = zero_bucket()
    total_entries = 0
    for key in keys:
        block = blocks[key]
        tokens = block_tokens(block)
        add_row(agg, tokens)
        total_entries += block.get("entries", 0) or 0
        start = (block.get("startTime") or "").replace("T", " ")[:16]
        models = ", ".join(short_model(m) for m in block.get("models", []))
        active = "yes" if block.get("isActive") else ""
        out.append(
            f"| {start} | {fmt_tokens(block.get('entries', 0))} | {token_cells(tokens)} | {models} | {active} |"
        )
    out.append(f"| **Total** | {fmt_tokens(total_entries)} | {token_cells(agg)} | | |")
    out.append("")
    return out


def render_markdown(history: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# ccusage — full usage log",
        "",
        f"_Last updated: {now} · generated by `scripts/ccusage_daily_log.py`_",
        "",
        "Jump to: [Sessions](#sessions) · [Daily](#daily) · [Weekly](#weekly) · "
        "[Monthly](#monthly) · [Whole usage](#whole-usage) · [Billing blocks](#billing-blocks)",
        "",
    ]
    lines += render_sessions_section(history["session"])
    lines += render_period_section("Daily", history["daily"], "Date", "day")
    lines += render_period_section("Weekly", history["weekly"], "Week Of", "week")
    lines += render_period_section("Monthly", history["monthly"], "Month", "month")
    lines += render_whole_usage(history)
    lines += render_blocks_section(history["blocks"])
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> None:
    history = load_history()
    merge_sections(history, fetch_sections())
    merge_blocks(history, fetch_blocks())
    save_history(history)
    MARKDOWN_PATH.write_text(render_markdown(history), encoding="utf-8")
    print(
        f"Logged {len(history['session'])} session(s), {len(history['daily'])} day(s), "
        f"{len(history['weekly'])} week(s), {len(history['monthly'])} month(s), "
        f"{len(history['blocks'])} block(s). See {MARKDOWN_PATH}"
    )


if __name__ == "__main__":
    main()
