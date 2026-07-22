"""Parse Cursor dashboard usage CSV exports (IDE + automation formats)."""

from __future__ import annotations

import csv
from pathlib import Path

from app.cursor_pricing import build_usage_import_key, estimate_token_cost_usd

AUTOMATION_HEADERS = frozenset({"Automation ID", "Cloud Agent ID"})
USAGE_EVENTS_HEADERS = AUTOMATION_HEADERS | {
    "Date",
    "Kind",
    "Input (w/ Cache Write)",
    "Input (w/o Cache Write)",
    "Cache Read",
    "Output Tokens",
    "Total Tokens",
}

ZERO_COST_LABELS = frozenset(
    {
        "included",
        "free",
        "errored, no charge",
        "errored no charge",
        "no charge",
    }
)


def _maybe_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def _first_value(row: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def is_usage_events_format(fieldnames: list[str] | None) -> bool:
    if not fieldnames:
        return False
    headers = set(fieldnames)
    return bool(AUTOMATION_HEADERS & headers)


def is_automation_row(row: dict[str, str]) -> bool:
    automation_id = (_first_value(row, "Automation ID", "automation_id") or "").strip()
    cloud_agent_id = (_first_value(row, "Cloud Agent ID", "cloud_agent_id", "cursor_run_id") or "").strip()
    return bool(automation_id or cloud_agent_id.startswith("bc-"))


def parse_cost_usd(raw: str | None) -> float | None:
    if raw in (None, ""):
        return None
    text = str(raw).strip().replace("$", "").replace(",", "")
    if text.lower() in ZERO_COST_LABELS:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return None


def _parse_tokens_usage_events(row: dict[str, str]) -> tuple[int | None, int | None]:
    output_tokens = _maybe_int(_first_value(row, "Output Tokens", "output_tokens"))
    total_tokens = _maybe_int(_first_value(row, "Total Tokens", "total_tokens"))
    if output_tokens is not None and total_tokens is not None and total_tokens >= output_tokens:
        return total_tokens - output_tokens, output_tokens

    input_with_cache = _maybe_int(_first_value(row, "Input (w/ Cache Write)")) or 0
    input_without_cache = _maybe_int(_first_value(row, "Input (w/o Cache Write)")) or 0
    cache_read = _maybe_int(_first_value(row, "Cache Read")) or 0
    input_tokens = input_with_cache + input_without_cache + cache_read
    if input_tokens == 0 and output_tokens is None:
        return None, None
    return input_tokens or None, output_tokens


def _parse_tokens_legacy(row: dict[str, str]) -> tuple[int | None, int | None]:
    return (
        _maybe_int(_first_value(row, "input_tokens", "Input Tokens")),
        _maybe_int(_first_value(row, "output_tokens", "Output Tokens")),
    )


def parse_usage_row(row: dict[str, str], *, usage_events_format: bool) -> dict | None:
    if usage_events_format:
        if not is_automation_row(row):
            return None
        cursor_run_id = (_first_value(row, "Cloud Agent ID", "cloud_agent_id", "cursor_run_id") or "").strip() or None
        automation_id = (_first_value(row, "Automation ID", "automation_id") or "").strip() or None
        model = _first_value(row, "Model", "model")
        timestamp = _first_value(row, "Date", "timestamp", "Timestamp")
        cost_usd = parse_cost_usd(_first_value(row, "Cost", "cost", "cost_usd", "charged"))
        input_tokens, output_tokens = _parse_tokens_usage_events(row)
    else:
        cursor_run_id = _first_value(row, "run_id", "Run ID", "cursor_run_id", "Cloud Agent ID")
        automation_id = _first_value(row, "Automation ID", "automation_id")
        model = _first_value(row, "model", "Model")
        timestamp = _first_value(row, "timestamp", "Timestamp", "Date")
        cost_usd = parse_cost_usd(_first_value(row, "cost", "Cost", "cost_usd", "charged"))
        input_tokens, output_tokens = _parse_tokens_legacy(row)

    if cost_usd is None and input_tokens is None and output_tokens is None:
        return None

    estimated_cost_usd = estimate_token_cost_usd(model, input_tokens, output_tokens)
    billed = cost_usd if cost_usd is not None else 0.0
    usage_import_key = build_usage_import_key(
        cursor_run_id=cursor_run_id,
        timestamp=timestamp,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=billed,
        automation_id=automation_id,
    )

    return {
        "cursor_run_id": cursor_run_id,
        "model": model,
        "cost_usd": billed,
        "estimated_cost_usd": estimated_cost_usd,
        "usage_import_key": usage_import_key,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "timestamp": timestamp,
    }


def load_cursor_usage_csv(
    csv_path: Path,
    *,
    automations_only: bool = True,
) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        usage_events_format = is_usage_events_format(reader.fieldnames)
        for row in reader:
            if automations_only and usage_events_format and not is_automation_row(row):
                continue
            parsed = parse_usage_row(row, usage_events_format=usage_events_format)
            if parsed is not None:
                rows.append(parsed)
    return rows
