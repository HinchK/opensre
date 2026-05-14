from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline import runners
from app.state import AgentState


def test_astream_investigation_swallows_futures_shutdown_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RuntimeError('cannot schedule new futures after shutdown') from LangGraph's
    thread pool during teardown must not propagate to the caller or be captured
    in Sentry — it is cleanup noise, not a real error."""
    import asyncio
    import types

    shutdown_err = RuntimeError("cannot schedule new futures after shutdown")
    captured: list[BaseException] = []

    async def _raising_astream(*_a: Any, **_kw: Any):  # type: ignore[return]
        raise shutdown_err
        yield  # make it an async generator

    fake_graph = types.SimpleNamespace(astream_events=_raising_astream)
    fake_graph_module = types.ModuleType("app.pipeline.graph")
    fake_graph_module.graph = fake_graph  # type: ignore[attr-defined]

    monkeypatch.setattr(runners, "init_sentry", lambda **_kw: None)
    monkeypatch.setattr(runners, "capture_exception", captured.append)

    async def _collect() -> list[Any]:
        events = []
        with patch.dict("sys.modules", {"app.pipeline.graph": fake_graph_module}):
            async for evt in runners.astream_investigation(
                alert_name="test", pipeline_name="test", severity="low"
            ):
                events.append(evt)
        return events

    result = asyncio.run(_collect())

    assert result == []
    assert captured == [], "shutdown RuntimeError must not be sent to Sentry"


def test_astream_investigation_captures_other_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-shutdown RuntimeErrors must still be captured and re-raised."""
    import asyncio
    import types

    other_err = RuntimeError("something unexpected")
    captured: list[BaseException] = []

    async def _raising_astream(*_a: Any, **_kw: Any):  # type: ignore[return]
        raise other_err
        yield

    fake_graph = types.SimpleNamespace(astream_events=_raising_astream)
    fake_graph_module = types.ModuleType("app.pipeline.graph")
    fake_graph_module.graph = fake_graph  # type: ignore[attr-defined]

    monkeypatch.setattr(runners, "init_sentry", lambda **_kw: None)
    monkeypatch.setattr(runners, "capture_exception", captured.append)

    async def _run() -> None:
        with patch.dict("sys.modules", {"app.pipeline.graph": fake_graph_module}):
            async for _ in runners.astream_investigation(
                alert_name="test", pipeline_name="test", severity="low"
            ):
                pass

    with pytest.raises(RuntimeError, match="something unexpected"):
        asyncio.run(_run())

    assert captured == [other_err]


def test_run_chat_initializes_sentry_and_captures_unhandled_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentry_init_calls: list[None] = []
    captured_errors: list[BaseException] = []
    expected_error = RuntimeError("router failed")

    def failing_router(_state: AgentState) -> dict[str, object]:
        raise expected_error

    monkeypatch.setattr(runners, "init_sentry", lambda **_kw: sentry_init_calls.append(None))
    monkeypatch.setattr(runners, "capture_exception", captured_errors.append)
    monkeypatch.setattr(runners, "router_node", failing_router)

    with pytest.raises(RuntimeError, match="router failed"):
        runners.run_chat(cast(AgentState, {}))

    assert sentry_init_calls == [None]
    assert captured_errors == [expected_error]
