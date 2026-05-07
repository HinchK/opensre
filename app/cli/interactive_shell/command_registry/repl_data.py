"""Lazy loaders for verified integrations and LLM settings (repl slash commands)."""

from __future__ import annotations

from typing import Any


def _list_row_from_record(record: dict[str, Any], *, source: str) -> dict[str, str] | None:
    service = str(record.get("service", "")).strip().lower()
    if not service:
        return None

    status = str(record.get("status", "active")).strip().lower() or "active"
    if status == "active":
        rendered_status = "configured"
        detail = f"Configured in {source}. Run /integrations verify to check connectivity."
    elif status in {"failed", "missing", "misconfigured"}:
        rendered_status = "failed" if status == "misconfigured" else status
        detail = "Stored integration needs attention."
    else:
        return None

    instances = record.get("instances")
    instance_count = len(instances) if isinstance(instances, list) else 0
    instance_detail = f" ({instance_count} instances)" if instance_count > 1 else ""
    return {
        "service": service,
        "source": source,
        "status": rendered_status,
        "detail": f"{detail}{instance_detail}",
    }


def load_list_integrations() -> list[dict[str, str]]:
    """Return local integration status without making network calls."""
    from app.integrations.catalog import load_env_integrations
    from app.integrations.store import load_integrations

    rows: list[dict[str, str]] = []
    seen_services: set[str] = set()

    for record in load_integrations():
        row = _list_row_from_record(record, source="local store")
        if row is None:
            continue
        rows.append(row)
        seen_services.add(row["service"])

    for record in load_env_integrations():
        row = _list_row_from_record(record, source="local env")
        if row is None or row["service"] in seen_services:
            continue
        rows.append(row)
        seen_services.add(row["service"])

    return rows


def load_verified_integrations() -> list[dict[str, str]]:
    """Import lazily so an unconfigured store doesn't slow down every REPL turn."""
    from app.integrations.verify import verify_integrations

    return verify_integrations()


def load_llm_settings() -> Any | None:
    """Best-effort LLM settings load; returns None if env is misconfigured."""
    try:
        from app.config import LLMSettings

        return LLMSettings.from_env()
    except Exception:
        return None


__all__ = ["load_list_integrations", "load_llm_settings", "load_verified_integrations"]
