"""Tests for the Discord report formatter."""

from __future__ import annotations

from app.delivery.publish_findings.formatters.discord import (
    format_discord_message,
)
from app.delivery.publish_findings.report_context import build_report_context


def _make_state() -> dict:
    return {
        "pipeline_name": "checkout-service",
        "alert_name": "Checkout latency spike",
        "root_cause": "Checkout service was throttled by the upstream API cluster.",
        "root_cause_category": "dependency_failure",
        "validity_score": 0.91,
        "severity": "critical",
        "validated_claims": [
            {
                "claim": "Grafana logs show repeated 500 responses.",
                "evidence_sources": ["grafana_logs"],
            }
        ],
        "non_validated_claims": [
            {"claim": "Database connection pool exhausted."},
        ],
        "investigation_recommendations": [],
        "remediation_steps": [
            "Increase memory limit for payments-api deployment",
        ],
        "available_sources": {
            "grafana": {
                "grafana_endpoint": "https://myorg.grafana.net",
                "service_name": "checkout-api",
            },
        },
        "evidence": {
            "grafana_logs": [
                {"message": "service unavailable"},
            ],
        },
    }


def test_format_discord_message_returns_content_and_embeds() -> None:
    ctx = build_report_context(_make_state())
    content, embeds = format_discord_message(ctx)

    assert content
    assert len(embeds) == 1
    assert "Checkout latency spike" in content


def test_discord_embed_has_required_fields() -> None:
    ctx = build_report_context(_make_state())
    content, embeds = format_discord_message(ctx)
    embed = embeds[0]

    assert embed["title"]
    assert embed["color"]
    assert embed["description"]
    assert embed["fields"]
    assert embed["footer"]


def test_discord_severity_color_for_critical() -> None:
    state = _make_state()
    state["severity"] = "critical"
    ctx = build_report_context(state)
    _, embeds = format_discord_message(ctx)

    assert embeds[0]["color"] == 15158332  # red


def test_discord_severity_color_for_warning() -> None:
    state = _make_state()
    state["severity"] = "warning"
    ctx = build_report_context(state)
    _, embeds = format_discord_message(ctx)

    assert embeds[0]["color"] == 15844367  # yellow


def test_discord_findings_field_present() -> None:
    ctx = build_report_context(_make_state())
    _, embeds = format_discord_message(ctx)
    field_names = [f["name"] for f in embeds[0]["fields"]]

    assert "Findings" in field_names


def test_discord_non_validated_field_present() -> None:
    ctx = build_report_context(_make_state())
    _, embeds = format_discord_message(ctx)
    field_names = [f["name"] for f in embeds[0]["fields"]]

    assert "Non-Validated Claims (Inferred)" in field_names


def test_discord_remediation_field_present() -> None:
    ctx = build_report_context(_make_state())
    _, embeds = format_discord_message(ctx)
    field_names = [f["name"] for f in embeds[0]["fields"]]

    assert "Recommended Actions" in field_names


def test_discord_provenance_field_present() -> None:
    ctx = build_report_context(_make_state())
    _, embeds = format_discord_message(ctx)
    field_names = [f["name"] for f in embeds[0]["fields"]]

    assert "Provenance" in field_names


def test_discord_field_value_respects_1024_limit() -> None:
    state = _make_state()
    state["remediation_steps"] = ["A" * 2000]
    ctx = build_report_context(state)
    _, embeds = format_discord_message(ctx)

    for field in embeds[0]["fields"]:
        assert len(field["value"]) <= 1024


def test_discord_field_name_respects_256_limit() -> None:
    state = _make_state()
    ctx = build_report_context(state)
    _, embeds = format_discord_message(ctx)

    for field in embeds[0]["fields"]:
        assert len(field["name"]) <= 256


def test_discord_embed_description_respects_4096_limit() -> None:
    state = _make_state()
    state["root_cause"] = "X" * 5000
    ctx = build_report_context(state)
    _, embeds = format_discord_message(ctx)

    assert len(embeds[0]["description"]) <= 4096


def test_discord_max_25_fields() -> None:
    state = _make_state()
    state["validated_claims"] = [
        {"claim": f"Claim {i}", "evidence_sources": []}
        for i in range(30)
    ]
    ctx = build_report_context(state)
    _, embeds = format_discord_message(ctx)

    assert len(embeds[0]["fields"]) <= 25


def test_discord_empty_state_produces_minimal_embed() -> None:
    state = {
        "pipeline_name": "test",
        "alert_name": "Test alert",
        "root_cause": "",
        "validated_claims": [],
        "non_validated_claims": [],
        "remediation_steps": [],
        "available_sources": {},
        "evidence": {},
    }
    ctx = build_report_context(state)
    content, embeds = format_discord_message(ctx)

    assert content
    assert len(embeds) == 1
    assert embeds[0]["fields"] == []
