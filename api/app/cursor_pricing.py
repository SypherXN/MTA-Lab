"""Estimate effective Cursor usage cost from token counts.

Rates are imputed list prices for comparison when CSV rows show Included/Free.
Calibrate from on-demand overage rows in your usage export when available.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRates:
    input_usd_per_million: float
    output_usd_per_million: float
    notes: str = ""


# Default imputed rates ($/1M tokens). Adjust if your overage CSV implies different values.
DEFAULT_RATES = ModelRates(
    input_usd_per_million=0.30,
    output_usd_per_million=1.20,
    notes="Blended fallback from observed auto-model overage (~$0.35/1M total).",
)

MODEL_RATES: dict[str, ModelRates] = {
    "composer-2.5": ModelRates(0.25, 1.00, "Composer 2.5 imputed list rate."),
    "composer-2.5-fast": ModelRates(0.15, 0.60, "Composer 2.5 Fast imputed list rate."),
    "auto": ModelRates(0.30, 1.20, "Auto router imputed list rate."),
    "cursor-grok-4.5-high": ModelRates(0.50, 2.00, "Grok 4.5 high imputed list rate."),
    "grok-4.5-xhigh": ModelRates(0.60, 2.50, "Grok 4.5 xhigh imputed list rate."),
    "gpt-5.6-sol-xhigh": ModelRates(0.55, 2.20, "GPT imputed list rate."),
    "claude-sonnet-5-thinking-high": ModelRates(0.45, 1.80, "Claude Sonnet imputed list rate."),
}


def normalize_model_name(model: str | None) -> str:
    return (model or "").strip().lower()


def get_model_rates(model: str | None) -> ModelRates:
    key = normalize_model_name(model)
    if not key:
        return DEFAULT_RATES
    if key in MODEL_RATES:
        return MODEL_RATES[key]
    for name, rates in MODEL_RATES.items():
        if name in key or key in name:
            return rates
    return DEFAULT_RATES


def estimate_token_cost_usd(
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    if input_tokens is None and output_tokens is None:
        return None
    rates = get_model_rates(model)
    inp = max(int(input_tokens or 0), 0)
    out = max(int(output_tokens or 0), 0)
    if inp == 0 and out == 0:
        return None
    return round(
        (inp / 1_000_000) * rates.input_usd_per_million
        + (out / 1_000_000) * rates.output_usd_per_million,
        6,
    )


def effective_cost_usd(billed_cost_usd: float | None, estimated_cost_usd: float | None) -> float:
    billed = float(billed_cost_usd or 0)
    if billed > 0:
        return billed
    return float(estimated_cost_usd or 0)


def build_usage_import_key(
    *,
    cursor_run_id: str | None,
    timestamp: str | None,
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    cost_usd: float | None,
    automation_id: str | None = None,
) -> str:
    """Stable dedupe key for CSV re-imports and automation run usage rows."""
    cloud = (cursor_run_id or "").strip()
    ts = (timestamp or "").strip()
    if cloud:
        return f"cloud:{cloud}|{ts}"
    parts = [
        ts,
        (model or "").strip().lower(),
        str(input_tokens or 0),
        str(output_tokens or 0),
        f"{float(cost_usd or 0):.6f}",
        (automation_id or "").strip(),
    ]
    return "row:" + "|".join(parts)
