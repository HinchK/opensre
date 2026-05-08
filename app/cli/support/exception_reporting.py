"""Shared exception reporting policy for CLI and interactive-shell boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import click

from app.cli.support.errors import OpenSREError
from app.services.llm_client import LLMOperationalError
from app.utils.sentry_sdk import capture_exception


def should_report_exception(exc: BaseException, *, expected: bool = False) -> bool:
    """Return whether a caught exception should be reported to Sentry."""
    if expected:
        return False
    if isinstance(exc, (KeyboardInterrupt, EOFError, OpenSREError, click.Abort)):
        return False
    if isinstance(exc, click.UsageError):
        return False
    # LLMOperationalError covers auth failures, rate limits, quota exhaustion,
    # model-not-found, and API overloads — user or infrastructure issues, not bugs.
    return not isinstance(exc, LLMOperationalError)


def report_exception(
    exc: BaseException,
    *,
    context: str,
    extra: Mapping[str, Any] | None = None,
    expected: bool = False,
) -> bool:
    """Best-effort Sentry report for swallowed boundary exceptions."""
    if not should_report_exception(exc, expected=expected):
        return False
    capture_exception(exc, context=context, extra=extra)
    return True


__all__ = ["report_exception", "should_report_exception"]
