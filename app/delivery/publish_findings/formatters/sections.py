"""Channel-agnostic report section builders.

Extracts structured sections from a ReportContext once, so each channel
formatter (Slack mrkdwn, Telegram HTML, Discord embeds) only applies its
own markup without duplicating claim rendering, provenance formatting, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.delivery.publish_findings.formatters.evidence import (
    format_cited_evidence_section,
    format_cited_evidence_section_html,
)
from app.delivery.publish_findings.formatters.infrastructure import (
    build_investigation_trace,
)
from app.delivery.publish_findings.report_context import ReportContext
from app.delivery.publish_findings.urls.aws import build_cloudwatch_url

# ---------------------------------------------------------------------------
# Structured section data
# ---------------------------------------------------------------------------


@dataclass
class EvidenceRef:
    """A single evidence reference with optional URL."""

    display_id: str
    url: str | None = None


@dataclass
class ClaimLine:
    """A single claim bullet with optional evidence references."""

    text: str
    evidence_refs: list[EvidenceRef] = field(default_factory=list)


@dataclass
class ReportSections:
    """All logical sections of an RCA report, channel-agnostic."""

    header: str
    root_cause: str
    top_log: str | None
    findings: list[ClaimLine]
    non_validated: list[str]
    correlation_signals: list[str]
    correlation_drivers: list[str]
    provenance: list[str]
    remediation: list[str]
    trace: list[str]
    evidence_citations_plain: str
    evidence_citations_html: str
    cloudwatch_plain: str
    cloudwatch_html: str
    meta_plain: str
    meta_html: str


# ---------------------------------------------------------------------------
# Shared helpers (moved from report.py to avoid duplication)
# ---------------------------------------------------------------------------

_EVIDENCE_LOG_KEYS: dict[str, list[str]] = {
    "datadog_logs": ["datadog_error_logs", "datadog_logs"],
    "datadog": ["datadog_error_logs", "datadog_logs"],
    "grafana_logs": ["grafana_error_logs", "grafana_logs"],
    "grafana": ["grafana_error_logs", "grafana_logs"],
    "cloudwatch_logs": ["cloudwatch_logs"],
    "cloudwatch": ["cloudwatch_logs"],
}


def _extract_log_message(entry: object) -> str:
    if isinstance(entry, dict):
        return (entry.get("message") or "").strip()
    return str(entry).strip()


def _get_top_error_log(evidence: dict) -> str | None:
    for key in (
        "datadog_error_logs",
        "datadog_logs",
        "grafana_error_logs",
        "grafana_logs",
        "cloudwatch_logs",
    ):
        logs = evidence.get(key) or []
        if logs:
            msg = _extract_log_message(logs[0])
            if msg:
                return msg
    return None


def _resolve_evidence_tags(text: str, evidence: dict) -> str:
    import re

    def _replace(m: re.Match) -> str:
        source = m.group(1).strip().lower()
        for key in _EVIDENCE_LOG_KEYS.get(source, []):
            logs = evidence.get(key) or []
            if logs:
                msg = _extract_log_message(logs[0])
                if msg:
                    return f": `{msg}`"
        return ""

    return re.sub(r"\s*\[(?i:evidence):\s*([^\]]+)\]", _replace, text).strip()


def _sanitize_for_slack(text: str) -> str:
    import re

    result = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
    result = re.sub(r"\*\*(.+?)\*\*", r"*\1*", result)
    return result


def _first_sentence(text: str) -> str:
    import re

    cleaned = re.sub(r"(?:^|\s)#{1,6}\s+", " ", text, flags=re.MULTILINE)
    cleaned = re.sub(
        r"\b(?:Problem Statement|Summary|Context|Description|Overview)\b[:\s]*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    normalized = " ".join(cleaned.split()).strip()
    if not normalized:
        return ""
    parts = re.split(r"(?<=[.?!])\s+", normalized, maxsplit=1)
    sentence = parts[0].rstrip(".?!")
    return sentence


def _is_speculative(text: str) -> bool:
    speculative_terms = (" may ", " might ", " possibly", " possible ", " likely ")
    lower = f" {text.lower()} "
    return any(term in lower for term in speculative_terms)


def _remove_speculative_words(text: str) -> str:
    speculative = ("may", "might", "likely", "probably", "possibly")
    words = text.split()
    filtered = [w for w in words if w.lower() not in speculative]
    return " ".join(filtered)


def _derive_root_cause_sentence(ctx: ReportContext) -> str:
    import re

    root_cause_text = ctx.get("root_cause", "") or ""
    root_cause_text = re.sub(r"\s*\[(?i:evidence):[^\]]*\]", "", root_cause_text).strip()
    validated_claims = ctx.get("validated_claims", [])

    if root_cause_text:
        sentence = _first_sentence(root_cause_text)
        if sentence and not _is_speculative(sentence):
            return sentence

    causal_connectors = (
        " because ",
        " due to ",
        " caused ",
        " resulted in ",
        " led to ",
        " root cause ",
        " failure triggered ",
    )

    for claim_data in validated_claims:
        claim = claim_data.get("claim", "") or ""
        claim = re.sub(r"\s*\[(?i:evidence):[^\]]*\]", "", claim).strip()
        lower = f" {claim.lower()} "
        if any(connector in lower for connector in causal_connectors):
            sentence = _first_sentence(claim)
            if sentence:
                return _first_sentence(_remove_speculative_words(sentence))

    if root_cause_text:
        sentence = _first_sentence(root_cause_text)
        if sentence:
            return sentence

    if validated_claims:
        claim = validated_claims[0].get("claim", "") or ""
        claim = re.sub(r"\s*\[(?i:evidence):[^\]]*\]", "", claim).strip()
        sentence = _first_sentence(claim)
        if sentence:
            return sentence

    return ""


def _format_provenance_lines(ctx: ReportContext) -> list[str]:
    provenance = ctx.get("source_provenance") or {}
    lines: list[str] = []
    for source_name, entry in provenance.items():
        label = entry.get("label") or source_name.title()
        summary = entry.get("summary") or ""
        if summary:
            lines.append(f"• {label}: {summary}")
    return lines


def _format_correlation_lines(ctx: ReportContext) -> tuple[list[str], list[str]]:
    correlation = ctx.get("correlation") or {}
    if not isinstance(correlation, dict):
        return [], []

    raw_signals = correlation.get("correlated_signals") or []
    raw_drivers = correlation.get("most_likely_causal_drivers") or []

    signal_lines: list[str] = []
    for signal in raw_signals:
        if not isinstance(signal, dict):
            continue
        name = signal.get("name") or "unknown"
        source = signal.get("source") or "unknown"
        score = signal.get("score")
        score_text = f" score={float(score):.2f}" if isinstance(score, int | float) else ""
        signal_lines.append(f"• {name} ({source}{score_text})")

    driver_lines: list[str] = []
    for driver in raw_drivers:
        if not isinstance(driver, dict):
            continue
        name = driver.get("name") or "unknown"
        confidence = driver.get("confidence")
        rationale = driver.get("rationale") or ""
        confidence_text = (
            f" confidence={float(confidence):.2f}" if isinstance(confidence, int | float) else ""
        )
        suffix = f" — {_sanitize_for_slack(str(rationale))}" if rationale else ""
        driver_lines.append(f"• {name}{confidence_text}{suffix}")

    return signal_lines, driver_lines


def _render_claim_lines(ctx: ReportContext) -> tuple[list[ClaimLine], list[str]]:
    """Return (validated_claim_lines, non_validated_texts) from shared context.

    This is the single source of truth for claim rendering — both Slack and
    Telegram formatters consume this instead of maintaining separate copies.
    """
    catalog = ctx.get("evidence_catalog") or {}
    evidence = ctx.get("evidence") or {}

    validated_lines: list[ClaimLine] = []
    for claim_data in ctx.get("validated_claims", []):
        claim = claim_data.get("claim", "")
        claim = _resolve_evidence_tags(claim, evidence)
        claim = _sanitize_for_slack(claim)
        evidence_ids = claim_data.get("evidence_ids", [])
        evidence_labels = claim_data.get("evidence_labels", [])
        evidence_refs: list[EvidenceRef] = []
        if evidence_ids:
            for eid in evidence_ids:
                entry = catalog.get(eid, {})
                disp = entry.get("display_id", eid)
                url = entry.get("url")
                evidence_refs.append(EvidenceRef(display_id=disp, url=url or None))
        elif evidence_labels:
            evidence_refs = [EvidenceRef(display_id=str(x)) for x in evidence_labels]
        validated_lines.append(ClaimLine(text=claim, evidence_refs=evidence_refs))

    non_validated_lines: list[str] = [
        _sanitize_for_slack(cd.get("claim", "")) for cd in ctx.get("non_validated_claims", [])
    ]

    return validated_lines, non_validated_lines


def _render_cloudwatch_plain(ctx: ReportContext) -> str:
    cw_url = ctx.get("cloudwatch_logs_url")
    cw_group = ctx.get("cloudwatch_log_group")
    cw_stream = ctx.get("cloudwatch_log_stream")

    if cw_url:
        return "\n*CloudWatch Logs*\n"
    elif cw_group and cw_stream:
        url = build_cloudwatch_url(ctx)
        if url:
            return "\n*CloudWatch Logs*\n"
        return f"\n*CloudWatch Logs:*\n* Log Group: {cw_group}\n* Log Stream: {cw_stream}\n"
    return ""


def _render_cloudwatch_html(ctx: ReportContext) -> str:
    import html as html_mod

    cw_url = ctx.get("cloudwatch_logs_url")
    cw_group = ctx.get("cloudwatch_log_group")
    cw_stream = ctx.get("cloudwatch_log_stream")

    if cw_url:
        safe = html_mod.escape(str(cw_url), quote=True)
        return f'\n<b>CloudWatch</b>: <a href="{safe}">View logs</a>\n'
    if cw_group and cw_stream:
        url = build_cloudwatch_url(ctx)
        if url:
            safe = html_mod.escape(str(url), quote=True)
            return f'\n<b>CloudWatch</b>: <a href="{safe}">View logs</a>\n'
        return (
            f"\n<b>CloudWatch Logs</b>\n"
            f"Log Group: {html_mod.escape(str(cw_group))}\n"
            f"Log Stream: {html_mod.escape(str(cw_stream))}\n"
        )
    return ""


def _render_meta_plain(ctx: ReportContext) -> str:
    duration_seconds = ctx.get("investigation_duration_seconds")
    alert_id = ctx.get("alert_id")
    meta_lines: list[str] = []
    if duration_seconds is not None:
        meta_lines.append(f"Timing: {duration_seconds}s")
    if alert_id:
        meta_lines.append(f"Alert ID: {alert_id}")
    return "\n".join(meta_lines)


def _render_meta_html(ctx: ReportContext) -> str:
    import html as html_mod

    duration_seconds = ctx.get("investigation_duration_seconds")
    alert_id = ctx.get("alert_id")
    meta_bits: list[str] = []
    if duration_seconds is not None:
        meta_bits.append(f"Timing: {duration_seconds}s")
    if alert_id:
        meta_bits.append(f"Alert ID: {alert_id}")
    return html_mod.escape(" | ".join(meta_bits)) if meta_bits else ""


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_report_sections(ctx: ReportContext) -> ReportSections:
    """Extract all logical report sections from context (channel-agnostic)."""

    evidence = ctx.get("evidence") or {}

    root_cause_sentence = (
        _derive_root_cause_sentence(ctx) or "Not determined (insufficient evidence)."
    )
    top_log = _get_top_error_log(evidence)

    validated_claims, non_validated = _render_claim_lines(ctx)
    provenance = _format_provenance_lines(ctx)
    corr_signals, corr_drivers = _format_correlation_lines(ctx)
    trace = build_investigation_trace(ctx)

    evidence_plain = format_cited_evidence_section(ctx).strip()
    evidence_html = format_cited_evidence_section_html(ctx).strip()
    cw_plain = _render_cloudwatch_plain(ctx).strip()
    cw_html = _render_cloudwatch_html(ctx).strip()
    meta_plain = _render_meta_plain(ctx)
    meta_html = _render_meta_html(ctx)

    return ReportSections(
        header="",
        root_cause=root_cause_sentence,
        top_log=top_log,
        findings=validated_claims,
        non_validated=non_validated,
        correlation_signals=corr_signals,
        correlation_drivers=corr_drivers,
        provenance=provenance,
        remediation=ctx.get("remediation_steps", []),
        trace=trace,
        evidence_citations_plain=evidence_plain,
        evidence_citations_html=evidence_html,
        cloudwatch_plain=cw_plain,
        cloudwatch_html=cw_html,
        meta_plain=meta_plain,
        meta_html=meta_html,
    )
