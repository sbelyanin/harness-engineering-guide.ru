#!/usr/bin/env python3
"""harness-metrics-exporter: JSON-lines логи harness → Prometheus exposition format.

Только Python stdlib. Стримит файл построчно — O(1) RAM.

Использование:
    python3 export.py --input /var/log/harness/2026-07-20.jsonl
    python3 export.py --input current.jsonl --window-minutes 5 --output harness.prom

Формат лога: одна JSON-запись на строку, поля см. SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional


# Harness-специфичные buckets (см. SKILL.md «Buckets»).
BUCKETS = {
    "duration":      [0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
    "llm_latency":   [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
    "iterations":    [1, 3, 5, 10, 20, 50],
    "cost":          [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
}

VALID_STATUS = {"success", "error", "refusal", "timeout", "cancelled"}


@dataclass
class Histogram:
    buckets: list[float]
    counts: list[int] = field(default_factory=list)
    sum_: float = 0.0
    count: int = 0

    def __post_init__(self) -> None:
        # +Inf bucket добавляется автоматически
        self.counts = [0] * (len(self.buckets) + 1)

    def observe(self, value: float) -> None:
        self.sum_ += value
        self.count += 1
        for i, le in enumerate(self.buckets):
            if value <= le:
                self.counts[i] += 1
        # +Inf bucket
        self.counts[-1] += 1


@dataclass
class Metrics:
    requests_total: Counter = field(default_factory=Counter)
    errors_total: Counter = field(default_factory=Counter)
    tokens_consumed: Counter = field(default_factory=Counter)  # {(kind, policy): count}
    tool_calls_total: Counter = field(default_factory=Counter)
    guardrails_tripped: Counter = field(default_factory=Counter)
    request_duration: Histogram = field(
        default_factory=lambda: Histogram(BUCKETS["duration"])
    )
    llm_latency: dict[tuple[str, str], Histogram] = field(default_factory=dict)
    agent_iterations: Histogram = field(
        default_factory=lambda: Histogram(BUCKETS["iterations"])
    )
    cost_total: float = 0.0
    cost_distribution: Histogram = field(
        default_factory=lambda: Histogram(BUCKETS["cost"])
    )
    records_seen: int = 0
    records_skipped: int = 0


def parse_ts(ts: str) -> float:
    """ISO 8601 → unix timestamp. Лучше использовать datetime.fromisoformat,
    но он не понимает 'Z' до Python 3.11. Обрабатываем вручную."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        from datetime import datetime
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return 0.0


def iter_records(
    path: str, window_minutes: Optional[int]
) -> Iterable[dict]:
    """Стримит JSONL-файл построчно. Если window_minutes задан — только записи
    за последние N минут от «сейчас»."""
    cutoff = time.time() - window_minutes * 60 if window_minutes else None

    if path == "-":
        fh = sys.stdin
    else:
        fh = open(path, "r", encoding="utf-8")

    try:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if cutoff is not None:
                ts = parse_ts(rec.get("ts", ""))
                if ts < cutoff:
                    continue
            yield rec
    finally:
        if path != "-":
            fh.close()


def update(metrics: Metrics, rec: dict) -> None:
    status = rec.get("status", "unknown")
    if status not in VALID_STATUS:
        status = "error"
    metrics.requests_total[status] += 1

    # Errors по классам
    if status == "error":
        cls = rec.get("error_class") or "unknown"
        metrics.errors_total[cls] += 1

    # Tokens
    tokens = rec.get("tokens") or {}
    policy = rec.get("policy", "paid")
    for kind in ("prompt", "output", "cached"):
        val = tokens.get(kind, 0)
        if val:
            metrics.tokens_consumed[(kind, policy)] += val

    # Duration
    duration = rec.get("duration_s")
    if isinstance(duration, (int, float)) and duration >= 0:
        metrics.request_duration.observe(float(duration))

    # LLM latency (per-model)
    llm_lat = rec.get("llm_latency_s")
    model = rec.get("model", "unknown")
    provider = rec.get("provider", "unknown")
    if isinstance(llm_lat, (int, float)) and llm_lat >= 0:
        key = (model, provider)
        if key not in metrics.llm_latency:
            metrics.llm_latency[key] = Histogram(BUCKETS["llm_latency"])
        metrics.llm_latency[key].observe(float(llm_lat))

    # Iterations
    iters = rec.get("iterations")
    if isinstance(iters, int) and iters >= 0:
        metrics.agent_iterations.observe(float(iters))

    # Cost
    cost = rec.get("cost_usd")
    if isinstance(cost, (int, float)) and cost >= 0:
        metrics.cost_total += float(cost)
        metrics.cost_distribution.observe(float(cost))

    # Tool calls
    for tc in rec.get("tool_calls") or []:
        name = tc.get("name", "unknown")
        tstatus = tc.get("status", "unknown")
        metrics.tool_calls_total[(name, tstatus)] += 1

    # Guardrails
    for rule in rec.get("guardrails_tripped") or []:
        metrics.guardrails_tripped[rule] += 1

    metrics.records_seen += 1


def format_histogram(
    name: str, h: Histogram, labels: Optional[dict] = None
) -> list[str]:
    """Вывод одной гистограммы в exposition format."""
    lines = []
    label_str = ""
    if labels:
        label_str = (
            "{"
            + ",".join(f'{k}="{v}"' for k, v in labels.items())
            + "}"
        )

    for i, le in enumerate(h.buckets):
        bucket_labels = dict(labels or {})
        bucket_labels["le"] = _fmt_le(le)
        bucket_str = (
            "{"
            + ",".join(f'{k}="{v}"' for k, v in bucket_labels.items())
            + "}"
        )
        lines.append(f"{name}_bucket{bucket_str} {h.counts[i]}")

    inf_labels = dict(labels or {})
    inf_labels["le"] = "+Inf"
    inf_str = (
        "{" + ",".join(f'{k}="{v}"' for k, v in inf_labels.items()) + "}"
    )
    lines.append(f"{name}_bucket{inf_str} {h.counts[-1]}")
    lines.append(f"{name}_sum{label_str} {h.sum_}")
    lines.append(f"{name}_count{label_str} {h.count}")
    return lines


def _fmt_le(le: float) -> str:
    if le == int(le):
        return str(int(le))
    return str(le)


def render(metrics: Metrics) -> str:
    """Полный exposition format для всех метрик."""
    out = []

    # requests_total
    out.append("# HELP harness_requests_total Total harness requests by outcome")
    out.append("# TYPE harness_requests_total counter")
    for status, count in sorted(metrics.requests_total.items()):
        out.append(f'harness_requests_total{{status="{status}"}} {count}')
    out.append("")

    # errors_total
    out.append("# HELP harness_errors_total Errors by class")
    out.append("# TYPE harness_errors_total counter")
    for cls, count in sorted(metrics.errors_total.items()):
        out.append(f'harness_errors_total{{class="{cls}"}} {count}')
    out.append("")

    # tokens_consumed_total
    out.append(
        "# HELP harness_tokens_consumed_total Tokens consumed by kind and policy"
    )
    out.append("# TYPE harness_tokens_consumed_total counter")
    for (kind, policy), val in sorted(metrics.tokens_consumed.items()):
        out.append(
            f'harness_tokens_consumed_total{{kind="{kind}",policy="{policy}"}} {val}'
        )
    out.append("")

    # request_duration histogram
    out.append(
        "# HELP harness_request_duration_seconds Wall-clock harness request duration"
    )
    out.append("# TYPE harness_request_duration_seconds histogram")
    out.extend(format_histogram("harness_request_duration_seconds", metrics.request_duration))
    out.append("")

    # llm_latency (per-model)
    out.append(
        "# HELP harness_llm_latency_seconds LLM call latency by model and provider"
    )
    out.append("# TYPE harness_llm_latency_seconds histogram")
    for (model, provider), h in sorted(metrics.llm_latency.items()):
        out.extend(
            format_histogram(
                "harness_llm_latency_seconds",
                h,
                labels={"model": model, "provider": provider},
            )
        )
    out.append("")

    # agent_iterations
    out.append(
        "# HELP harness_agent_iterations_per_session Distribution of iterations per session"
    )
    out.append("# TYPE harness_agent_iterations_per_session histogram")
    out.extend(
        format_histogram("harness_agent_iterations_per_session", metrics.agent_iterations)
    )
    out.append("")

    # cost_total
    out.append("# HELP harness_request_cost_usd_total Total estimated USD cost")
    out.append("# TYPE harness_request_cost_usd_total counter")
    out.append(f"harness_request_cost_usd_total {metrics.cost_total}")
    out.append("")

    # cost distribution
    out.append(
        "# HELP harness_request_cost_usd Distribution of per-request cost"
    )
    out.append("# TYPE harness_request_cost_usd histogram")
    out.extend(format_histogram("harness_request_cost_usd", metrics.cost_distribution))
    out.append("")

    # tool_calls_total
    out.append("# HELP harness_tool_calls_total Tool calls by name and status")
    out.append("# TYPE harness_tool_calls_total counter")
    for (name, status), count in sorted(metrics.tool_calls_total.items()):
        out.append(
            f'harness_tool_calls_total{{name="{name}",status="{status}"}} {count}'
        )
    out.append("")

    # guardrails_tripped_total
    out.append("# HELP harness_guardrails_tripped_total Guardrail hits by rule")
    out.append("# TYPE harness_guardrails_tripped_total counter")
    for rule, count in sorted(metrics.guardrails_tripped.items()):
        out.append(f'harness_guardrails_tripped_total{{rule="{rule}"}} {count}')
    out.append("")

    return "\n".join(out) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="JSON-lines логи harness → Prometheus exposition format"
    )
    p.add_argument(
        "--input",
        "-i",
        required=True,
        help="JSONL-файл с логами, или '-' для stdin",
    )
    p.add_argument(
        "--window-minutes",
        "-w",
        type=int,
        default=None,
        help="Только записи за последние N минут (по полю ts)",
    )
    p.add_argument(
        "--output",
        "-o",
        default="-",
        help="Выходной файл (по умолчанию stdout)",
    )
    args = p.parse_args(argv)

    metrics = Metrics()
    for rec in iter_records(args.input, args.window_minutes):
        update(metrics, rec)

    output = render(metrics)

    if args.output == "-":
        sys.stdout.write(output)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)

    print(
        f"# processed: {metrics.records_seen} records, "
        f"{metrics.records_skipped} skipped",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
