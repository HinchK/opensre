"""Tests for the channel-agnostic section builders."""

from __future__ import annotations

from app.delivery.publish_findings.formatters.sections import (
    ClaimLine,
    EvidenceRef,
    build_report_sections,
)
from app.delivery.publish_findings.report_context import build_report_context


def _make_state() -> dict:
    return {
        "pipeline_name": "checkout-service",
        "alert_name": "Checkout latency spike",
        "root_cause": "Checkout service was throttled by the upstream API cluster.",
        "root_cause_category": "dependency_failure",
        "validity_score": 0.91,
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
            "Add Datadog monitor for memory usage at 80% threshold",
        ],
        "available_sources": {
            "grafana": {
                "grafana_endpoint": "https://myorg.grafana.net",
                "service_name": "checkout-api",
                "pipeline_name": "checkout-service",
            },
            "eks": {
                "cluster_name": "prod-cluster",
                "namespace": "payments",
                "region": "us-east-1",
            },
        },
        "evidence": {
            "grafana_logs": [
                {"message": "service unavailable"},
            ],
        },
    }


def test_build_report_sections_returns_all_fields() -> None:
    ctx = build_report_context(_make_state())
    sections = build_report_sections(ctx)

    assert sections.root_cause
    assert sections.findings
    assert sections.non_validated
    assert sections.remediation
    assert isinstance(sections.findings[0], ClaimLine)


def test_findings_include_evidence_refs() -> None:
    ctx = build_report_context(_make_state())
    sections = build_report_sections(ctx)

    assert len(sections.findings) == 1
    claim = sections.findings[0]
    assert "500 responses" in claim.text
    assert claim.evidence_refs  # E1 from catalog
    assert isinstance(claim.evidence_refs[0], EvidenceRef)
    assert claim.evidence_refs[0].display_id == "E1"


def test_findings_preserve_evidence_urls() -> None:
    state = _make_state()
    state["evidence"]["datadog_logs"] = [{"message": "5xx spike"}]
    state["available_sources"]["datadog"] = {"site": "datadoghq.com"}
    ctx = build_report_context(state)
    sections = build_report_sections(ctx)

    for claim in sections.findings:
        for ref in claim.evidence_refs:
            if ref.url:
                assert ref.url.startswith("http")


def test_non_validated_claims_are_sanitized() -> None:
    ctx = build_report_context(_make_state())
    sections = build_report_sections(ctx)

    assert len(sections.non_validated) == 1
    assert "Database connection pool exhausted" in sections.non_validated[0]


def test_provenance_lines_populated() -> None:
    ctx = build_report_context(_make_state())
    sections = build_report_sections(ctx)

    assert any("Grafana" in p for p in sections.provenance)
    assert any("AWS EKS" in p for p in sections.provenance)


def test_remediation_steps_passed_through() -> None:
    ctx = build_report_context(_make_state())
    sections = build_report_sections(ctx)

    assert len(sections.remediation) == 2
    assert "Increase memory limit" in sections.remediation[0]


def test_empty_sections_when_no_data() -> None:
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
    sections = build_report_sections(ctx)

    assert not sections.findings
    assert not sections.non_validated
    assert not sections.provenance
    assert not sections.remediation
    assert not sections.trace
    assert not sections.evidence_citations_plain


def test_root_cause_derived_when_empty() -> None:
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
    sections = build_report_sections(ctx)

    assert sections.root_cause == "Not determined (insufficient evidence)."
