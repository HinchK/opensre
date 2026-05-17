"""Discord report formatter — converts ReportContext into Discord embeds.

Discord uses embeds with fields rather than mrkdwn or HTML. Each section
becomes an embed field, respecting Discord's limits:
- Field name: 256 chars max
- Field value: 1024 chars max
- Embed description: 4096 chars max
- Max 25 fields per embed
- Total embed characters: 6000 max
"""

from __future__ import annotations

from typing import Any

from app.delivery.publish_findings.formatters.sections import (
    build_report_sections,
)
from app.delivery.publish_findings.report_context import ReportContext

_DISCORD_FIELD_VALUE_LIMIT = 1024
_DISCORD_EMBED_DESC_LIMIT = 4096
_DISCORD_MAX_FIELDS = 25

_SEVERITY_COLORS: dict[str, int] = {
    "critical": 15158332,
    "crit": 15158332,
    "high": 15105570,
    "error": 15105570,
    "medium": 15844367,
    "warning": 15844367,
    "warn": 15844367,
    "low": 5763719,
    "info": 5763719,
    "none": 9807270,
    "healthy": 5763719,
    "normal": 5763719,
}


def _truncate(value: str, limit: int, suffix: str = "…") -> str:
    if len(value) <= limit:
        return value
    room = limit - len(suffix)
    return value[:room] + suffix if room > 0 else suffix[:limit]


def _format_field_value(lines: list[str], prefix: str = "") -> str:
    """Join lines into a Discord-safe field value, truncated to limit."""
    text = prefix + "\n".join(lines)
    return _truncate(text, _DISCORD_FIELD_VALUE_LIMIT)


def _severity_color(ctx: ReportContext) -> int:
    raw = (ctx.get("severity") or "").strip().lower()
    return _SEVERITY_COLORS.get(raw, 9807270)


def format_discord_message(ctx: ReportContext) -> tuple[str, list[dict[str, Any]]]:
    """Format an RCA report for Discord.

    Returns (content_text, embeds) where embeds is a list of Discord embed dicts.
    The content_text is a short summary for the message body; the embeds carry
    the structured report sections.
    """
    sections = build_report_sections(ctx)
    alert_name = ctx.get("alert_name") or "Alert"
    pipeline_name = ctx.get("pipeline_name") or "unknown"
    duration_seconds = ctx.get("investigation_duration_seconds")
    alert_id = ctx.get("alert_id")

    content_text = f"**{alert_name}** — {pipeline_name}\n{sections.root_cause}"

    embed: dict[str, Any] = {
        "title": _truncate(f"{alert_name} — RCA Report", 256),
        "color": _severity_color(ctx),
        "description": _truncate(sections.root_cause, _DISCORD_EMBED_DESC_LIMIT),
        "fields": [],
        "footer": {"text": "OpenSRE Investigation"},
    }

    if sections.top_log:
        embed["fields"].append(
            {
                "name": "Top Error Log",
                "value": f"```\n{_truncate(sections.top_log, _DISCORD_FIELD_VALUE_LIMIT - 8)}\n```",
                "inline": False,
            }
        )

    if sections.findings:
        lines = []
        for c in sections.findings:
            ev = (
                f" [{', '.join(e.display_id for e in c.evidence_refs)}]"
                if c.evidence_refs
                else ""
            )
            lines.append(f"• {c.text}{ev}")
        embed["fields"].append(
            {
                "name": "Findings",
                "value": _format_field_value(lines),
                "inline": False,
            }
        )

    if sections.non_validated:
        lines = [f"• {raw}" for raw in sections.non_validated]
        embed["fields"].append(
            {
                "name": "Non-Validated Claims (Inferred)",
                "value": _format_field_value(lines),
                "inline": False,
            }
        )

    if sections.correlation_signals or sections.correlation_drivers:
        corr_lines: list[str] = []
        if sections.correlation_signals:
            corr_lines.append("**Correlated signals:**")
            corr_lines.extend(sections.correlation_signals)
        if sections.correlation_drivers:
            corr_lines.append("**Most likely causal drivers:**")
            corr_lines.extend(sections.correlation_drivers)
        embed["fields"].append(
            {
                "name": "Upstream Correlation",
                "value": _format_field_value(corr_lines),
                "inline": False,
            }
        )

    if sections.provenance:
        lines = [f"• {pl.lstrip('• ').strip()}" for pl in sections.provenance]
        embed["fields"].append(
            {
                "name": "Provenance",
                "value": _format_field_value(lines),
                "inline": False,
            }
        )

    if sections.remediation:
        lines = [f"• {s}" for s in sections.remediation]
        embed["fields"].append(
            {
                "name": "Recommended Actions",
                "value": _format_field_value(lines),
                "inline": False,
            }
        )

    if sections.trace:
        embed["fields"].append(
            {
                "name": "Investigation Trace",
                "value": _format_field_value(sections.trace),
                "inline": False,
            }
        )

    if sections.evidence_citations_plain:
        embed["fields"].append(
            {
                "name": "Cited Evidence",
                "value": _truncate(sections.evidence_citations_plain, _DISCORD_FIELD_VALUE_LIMIT),
                "inline": False,
            }
        )

    cw_url = ctx.get("cloudwatch_logs_url")
    if cw_url:
        embed["fields"].append(
            {
                "name": "CloudWatch",
                "value": f"[View logs]({cw_url})",
                "inline": False,
            }
        )

    meta_parts: list[str] = []
    if duration_seconds is not None:
        meta_parts.append(f"Analyzed in {duration_seconds}s")
    if alert_id:
        meta_parts.append(f"Alert: {alert_id}")
    if meta_parts:
        embed["footer"]["text"] = " | ".join(meta_parts)

    if len(embed["fields"]) > _DISCORD_MAX_FIELDS:
        embed["fields"] = embed["fields"][:_DISCORD_MAX_FIELDS]

    return content_text, [embed]
