"""RCA report formatting for Slack (mrkdwn / Block Kit) and Telegram (HTML).

All formatters consume shared section builders from sections.py so that
claim rendering, provenance formatting, correlation, etc. are defined once.
"""

import html
import re

from app.delivery.publish_findings.formatters.base import format_html_link, format_slack_link
from app.delivery.publish_findings.formatters.infrastructure import (
    format_pod_line,
    get_failed_pods,
)
from app.delivery.publish_findings.formatters.sections import (
    _derive_root_cause_sentence,
    _sanitize_for_slack,
    build_report_sections,
)
from app.delivery.publish_findings.report_context import ReportContext


def render_cloudwatch_link(ctx: ReportContext) -> str:
    """Render CloudWatch logs link for Slack mrkdwn."""
    cw_url = ctx.get("cloudwatch_logs_url")
    cw_group = ctx.get("cloudwatch_log_group")
    cw_stream = ctx.get("cloudwatch_log_stream")

    if cw_url:
        return f"\n*{format_slack_link('CloudWatch Logs', cw_url)}*\n"
    elif cw_group and cw_stream:
        from app.delivery.publish_findings.urls.aws import build_cloudwatch_url

        url = build_cloudwatch_url(ctx)
        view_link = format_slack_link("CloudWatch Logs", url) if url else None
        if view_link:
            return f"\n*{view_link}*\n"
        return f"\n*CloudWatch Logs:*\n* Log Group: {cw_group}\n* Log Stream: {cw_stream}\n"

    return ""


def render_cloudwatch_link_html(ctx: ReportContext) -> str:
    """Telegram-HTML CloudWatch deep link."""
    import html as html_mod

    from app.delivery.publish_findings.urls.aws import build_cloudwatch_url

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


_SLACK_LINK_RE = re.compile(r"<(https?://[^|>]+)(?:\|([^>]+))?>")


def _star_pairs_to_bold_placeholders(line: str, bold_ph: dict[str, str]) -> str:
    """Replace only paired ``*inner*`` spans (inner has no ``*``); lone ``*`` stay literal."""
    out = line
    while True:
        m = re.search(r"\*([^*\n]+)\*", out)
        if not m:
            break
        tok = f"«B{len(bold_ph)}»"
        bold_ph[tok] = "<b>" + html.escape(m.group(1)) + "</b>"
        out = out[: m.start()] + tok + out[m.end() :]
    return out


def _to_telegram_html_body(text: str) -> str:
    """Convert mixed Slack-style text (headers, *bold*, `code`, <url|label>) to Telegram HTML."""
    placeholders: dict[str, str] = {}

    def _put(chunk: str) -> str:
        token = f"«{len(placeholders)}»"
        placeholders[token] = chunk
        return token

    s = text
    s = re.sub(r"`([^`]+)`", lambda m: _put("<code>" + html.escape(m.group(1)) + "</code>"), s)
    s = _SLACK_LINK_RE.sub(
        lambda m: _put(format_html_link(m.group(2) or m.group(1), m.group(1))),
        s,
    )

    out_lines: list[str] = []
    for line in s.splitlines():
        hdr = re.match(r"^#{1,6}\s+(.+)$", line)
        if hdr:
            out_lines.append("<b>" + html.escape(hdr.group(1).strip()) + "</b>")
            continue
        bold_ph: dict[str, str] = {}
        starred = _star_pairs_to_bold_placeholders(line, bold_ph)
        escaped = html.escape(starred)
        for token, inner in sorted(bold_ph.items(), key=lambda kv: -len(kv[0])):
            escaped = escaped.replace(token, inner)
        out_lines.append(escaped)

    merged = "\n".join(out_lines)
    for token, chunk in sorted(placeholders.items(), key=lambda kv: -len(kv[0])):
        merged = merged.replace(token, chunk)
    return merged


def _norm_banner_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _telegram_baseline_repeats_header(ctx: ReportContext, root_cause_sentence: str) -> bool:
    """True when the derived root-cause line only repeats alert metadata already in the header."""
    alert = (ctx.get("alert_name") or "").strip()
    pipeline = (ctx.get("pipeline_name") or "").strip()
    if not alert or not pipeline:
        return False
    s = root_cause_sentence.strip()
    if len(s) > 220:
        return False
    rc = _norm_banner_key(s)
    if _norm_banner_key(alert) not in rc or _norm_banner_key(pipeline) not in rc:
        return False
    if "because" in rc or "due to" in rc or "caused" in rc:
        return False
    if "severity" in rc:
        return True
    return len(s) < 120


def _severity_telegram_header(ctx: ReportContext) -> str:
    """Severity emoji row aligned with Hermes Telegram sink conventions."""
    raw = (ctx.get("severity") or "").strip()
    lower = raw.lower()
    emoji = {
        "critical": "🔴",
        "crit": "🔴",
        "high": "🟠",
        "error": "🟠",
        "medium": "🟡",
        "warning": "🟡",
        "warn": "🟡",
        "low": "🟢",
        "info": "🟢",
        "none": "⚪",
        "healthy": "🟢",
        "normal": "🟢",
    }.get(lower, "⚠️")
    display_sev = raw.upper() if raw else "UNKNOWN"
    alert = html.escape(str(ctx.get("alert_name") or "Alert"))
    pipeline = html.escape(str(ctx.get("pipeline_name") or "unknown"))
    return f"{emoji} <b>{alert}</b> · {pipeline}\n<i>severity: {html.escape(display_sev)}</i>"


def _mrkdwn_section(text: str) -> "dict | None":
    """Build a Slack Block Kit section block with sanitized mrkdwn text.

    Slack section blocks have a 3000 char limit per text field.
    Returns None when text is empty — caller must skip None results.
    """
    sanitized = _sanitize_for_slack(text).strip()
    if not sanitized:
        return None
    if len(sanitized) > 2990:
        sanitized = sanitized[:2987] + "..."
    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": sanitized},
    }


# ---------------------------------------------------------------------------
# Telegram-specific formatting utilities
# ---------------------------------------------------------------------------


def format_slack_message(ctx: ReportContext) -> str:
    """Format a plain-text Slack message for the RCA report.

    Used as the `text` fallback (notifications, accessibility, terminal, ingest)
    when Block Kit blocks are the primary rendered content.
    """
    sections = build_report_sections(ctx)
    alert_id = ctx.get("alert_id")
    duration_seconds = ctx.get("investigation_duration_seconds")

    conclusion_block = f"{sections.root_cause}\n"
    if sections.top_log:
        conclusion_block += f"`{sections.top_log}`\n"

    if sections.findings:
        lines = [f"• {c.text} [{', '.join(c.evidence_refs)}]" if c.evidence_refs else f"• {c.text}" for c in sections.findings]
        conclusion_block += "\n## Findings\n" + "\n".join(lines) + "\n"
    if sections.non_validated:
        conclusion_block += (
            "\n*Non-Validated Claims (Inferred):*\n" + "\n".join(sections.non_validated) + "\n"
        )

    if sections.correlation_signals or sections.correlation_drivers:
        conclusion_block += "\n## Upstream Correlation\n"
        if sections.correlation_signals:
            conclusion_block += (
                "*Correlated signals:*\n" + "\n".join(sections.correlation_signals) + "\n"
            )
        if sections.correlation_drivers:
            conclusion_block += (
                "*Most likely causal drivers:*\n" + "\n".join(sections.correlation_drivers) + "\n"
            )

    provenance_block = ""
    if sections.provenance:
        provenance_block = (
            "\n*Provenance:*\n" + _sanitize_for_slack("\n".join(sections.provenance)) + "\n"
        )

    remediation_block = ""
    if sections.remediation:
        remediation_block = (
            "\n## Recommended Actions\n"
            + "\n".join(f"• {_sanitize_for_slack(s)}" for s in sections.remediation)
            + "\n"
        )

    trace_block = (
        "\n## Investigation Trace\n" + "\n".join(sections.trace) + "\n" if sections.trace else ""
    )

    cited_section = _sanitize_for_slack(sections.evidence_citations_plain)
    cloudwatch_link = render_cloudwatch_link(ctx)
    meta_lines = []
    if duration_seconds is not None:
        meta_lines.append(f"Timing: {duration_seconds}s")
    if alert_id:
        meta_lines.append(f"*Alert ID:* {alert_id}")
    meta_block = "\n" + "\n".join(meta_lines) if meta_lines else ""

    return f"""{conclusion_block}{provenance_block}{remediation_block}{trace_block}
{cited_section}
{cloudwatch_link}{meta_block}
"""


def format_telegram_message(ctx: ReportContext) -> str:
    """Format an HTML RCA message for Telegram (:meth:`parse_mode` ``HTML``).

    Uses Telegram-supported tags and a Hermes-style severity emoji header, instead
    of Slack mrkdwn (``<url|label>``, ``##`` headings) which render as plain text
    without ``parse_mode``.
    """
    sections = build_report_sections(ctx)
    duration_seconds = ctx.get("investigation_duration_seconds")
    alert_id = ctx.get("alert_id")
    derived_rc = _derive_root_cause_sentence(ctx)
    root_cause_sentence = derived_rc or "Not determined (insufficient evidence)."

    parts: list[str] = [_severity_telegram_header(ctx)]

    baseline_noise = (
        derived_rc
        and _telegram_baseline_repeats_header(ctx, derived_rc)
        and root_cause_sentence != "Not determined (insufficient evidence)."
    )
    if baseline_noise and not sections.top_log:
        pass
    elif baseline_noise and sections.top_log:
        parts.append("<code>" + html.escape(sections.top_log) + "</code>")
    else:
        rc = _to_telegram_html_body(root_cause_sentence)
        if sections.top_log:
            rc += "\n<code>" + html.escape(sections.top_log) + "</code>"
        parts.append(rc)

    if sections.findings:
        lines = []
        for c in sections.findings:
            ev_str = f" [{', '.join(c.evidence_refs)}]" if c.evidence_refs else ""
            lines.append(f"• {_to_telegram_html_body(c.text)}{ev_str}")
        parts.append("<b>Findings</b>\n" + "\n".join(lines))
    if sections.non_validated:
        parts.append("<b>Non-Validated Claims (Inferred)</b>\n" + "\n".join(
            f"• {_to_telegram_html_body(raw)}" for raw in sections.non_validated
        ))

    if sections.provenance:
        prov = "\n".join(
            "• " + _to_telegram_html_body(_sanitize_for_slack(pl.lstrip("• ").strip()))
            for pl in sections.provenance
        )
        parts.append("<b>Provenance</b>\n" + prov)

    if sections.remediation:
        ra = "\n".join(
            "• " + _to_telegram_html_body(_sanitize_for_slack(str(step)))
            for step in sections.remediation
        )
        parts.append("<b>Recommended Actions</b>\n" + ra)

    if sections.trace:
        tr = "\n".join(_to_telegram_html_body(step) for step in sections.trace)
        parts.append("<b>Investigation Trace</b>\n" + tr)

    if sections.evidence_citations_html:
        parts.append(sections.evidence_citations_html)

    if sections.cloudwatch_html:
        parts.append(sections.cloudwatch_html)

    meta_bits: list[str] = []
    if duration_seconds is not None:
        meta_bits.append(f"Timing: {duration_seconds}s")
    if alert_id:
        meta_bits.append(f"Alert ID: {alert_id}")
    if meta_bits:
        parts.append("<i>" + html.escape(" | ".join(meta_bits)) + "</i>")

    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Block Kit renderer (Slack interactive cards)
# ---------------------------------------------------------------------------


def build_slack_blocks(ctx: ReportContext) -> list[dict]:
    """Build Slack Block Kit blocks for the RCA report.

    Produces a clean, well-structured message using Slack's native
    formatting: header, sections with mrkdwn, dividers, and context blocks.
    """
    from typing import Any

    sections = build_report_sections(ctx)
    duration_seconds = ctx.get("investigation_duration_seconds")
    alert_id = ctx.get("alert_id")
    blocks: list[dict[str, Any]] = []

    def _add(block: "dict[str, Any] | None") -> None:
        if block is not None:
            blocks.append(block)

    # ── Root Cause
    rc_text = sections.root_cause
    if sections.top_log:
        rc_text += f"\n`{sections.top_log}`"
    _add(_mrkdwn_section(rc_text))

    # ── Failed Pods ──
    datadog_site = ctx.get("datadog_site", "datadoghq.com")
    all_pods = get_failed_pods(ctx)
    pod_lines = [
        line for p in all_pods[:5] if (line := format_pod_line(p, datadog_site, bullet="\u2022 "))
    ]
    if len(all_pods) > 5:
        pod_lines.append(f"• ... and {len(all_pods) - 5} more pods")
    if pod_lines:
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Failed Pods"},
            }
        )
        _add(_mrkdwn_section("\n".join(pod_lines)))

    # ── Validated Claims (Findings) and Non-Validated Claims ──
    if sections.findings:
        lines = [f"• {c.text} [{', '.join(c.evidence_refs)}]" if c.evidence_refs else f"• {c.text}" for c in sections.findings]
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Findings"},
            }
        )
        _add(_mrkdwn_section("\n".join(lines)))
    if sections.non_validated:
        _add(_mrkdwn_section("*Inferred (not yet validated)*\n" + "\n".join(sections.non_validated)))

    if sections.correlation_signals or sections.correlation_drivers:
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Upstream Correlation"},
            }
        )
        if sections.correlation_signals:
            _add(_mrkdwn_section("*Correlated signals:*\n" + "\n".join(sections.correlation_signals)))
        if sections.correlation_drivers:
            _add(
                _mrkdwn_section(
                    "*Most likely causal drivers:*\n" + "\n".join(sections.correlation_drivers)
                )
            )

    if sections.provenance:
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Provenance"},
            }
        )
        _add(_mrkdwn_section("\n".join(sections.provenance)))

    # ── Recommended Actions ──
    if sections.remediation:
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Recommended Actions"},
            }
        )
        _add(_mrkdwn_section("\n".join(f"• {_sanitize_for_slack(s)}" for s in sections.remediation)))

    # ── Investigation Trace ──
    if sections.trace:
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Investigation Trace"},
            }
        )
        _add(_mrkdwn_section("\n".join(sections.trace)))

    # ── Cited Evidence ──
    if sections.evidence_citations_plain:
        blocks.append({"type": "divider"})
        _add(_mrkdwn_section(sections.evidence_citations_plain))

    # ── CloudWatch link ──
    cw_link = render_cloudwatch_link(ctx).strip()
    if cw_link:
        _add(_mrkdwn_section(cw_link))

    # ── Meta context (duration / alert) at the bottom ──
    meta_parts = []
    if duration_seconds is not None:
        meta_parts.append(f"Analyzed in {duration_seconds}s")
    if alert_id:
        meta_parts.append(f"Alert: {alert_id}")
    if meta_parts:
        blocks.append({"type": "divider"})
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": " | ".join(meta_parts)}],
            }
        )

    # Slack hard-limits messages to 50 blocks — truncate from the middle to keep
    # the header (first block) and meta/actions (last 2 blocks) intact.
    if len(blocks) > 50:
        blocks = blocks[:48] + blocks[-2:]

    return blocks
