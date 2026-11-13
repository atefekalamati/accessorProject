"""Alert rules stay consistent with the metrics and the runbook (OPS-02, ADR-060)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from app.core.metrics import MetricsRegistry

ROOT = Path(__file__).parent.parent
RULES = ROOT / "ops" / "prometheus" / "alerts.yml"
RUNBOOK = ROOT / "docs" / "ops" / "ALERTS.md"
# PromQL functions and keywords used by the rules, and Prometheus' own scrape metric.
PROMQL = frozenset({"sum", "rate", "increase", "clamp_min", "time", "by", "e", "up"})
SEVERITIES = frozenset({"page", "ticket"})


def _rules() -> list[dict[str, Any]]:
    document = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    return [rule for group in document["groups"] for rule in group["rules"]]


def _exported_metrics() -> set[str]:
    registry = MetricsRegistry()
    registry.observe_request("GET", "/x", 200, 0.1)
    registry.rate_limited("ip")
    registry.payment_callback("paid")
    registry.job_succeeded("payment_reconcile")
    text = registry.render(
        {"database_up": ("", [((), 1.0)]), "payments_refund_required_open": ("", [((), 0.0)])}
    )
    return {line.split()[2] for line in text.splitlines() if line.startswith("# TYPE ")}


def _identifiers(expr: str) -> set[str]:
    stripped = re.sub(r"\{[^}]*\}", "", expr)  # label matchers
    stripped = re.sub(r"\[[^\]]*\]", "", stripped)  # range windows
    stripped = re.sub(r"\d+(\.\d+)?(e-?\d+)?", "", stripped)  # numbers
    return set(re.findall(r"[a-z_][a-z0-9_]*", stripped))


def test_every_rule_has_an_expression_severity_and_runbook() -> None:
    rules = _rules()
    assert rules
    for rule in rules:
        assert rule["alert"] and rule["expr"].strip(), rule
        assert rule["labels"]["severity"] in SEVERITIES, rule["alert"]
        assert rule["annotations"]["summary"], rule["alert"]
        assert rule["annotations"]["runbook"] == f"docs/ops/ALERTS.md#{rule['alert'].lower()}"


def test_every_rule_has_a_runbook_section_and_no_section_is_orphaned() -> None:
    sections = set(re.findall(r"^## (\w+)$", RUNBOOK.read_text(encoding="utf-8"), re.M))

    assert sections == {rule["alert"] for rule in _rules()}


def test_rules_only_use_metrics_the_api_exports() -> None:
    exported = {name.removesuffix("_total") for name in _exported_metrics()} | _exported_metrics()
    histogram_series = {
        f"http_request_duration_seconds_{suffix}" for suffix in ("bucket", "sum", "count")
    }
    for rule in _rules():
        unknown = _identifiers(rule["expr"]) - PROMQL - exported - histogram_series
        assert unknown == set(), (rule["alert"], unknown)


def test_job_alerts_name_jobs_the_api_reports() -> None:
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    for rule in _rules():
        for job in re.findall(r'job="([a-z_]+)"', rule["expr"]):
            if job != "project-ak-api":
                assert f'job_succeeded("{job}")' in main, (rule["alert"], job)
