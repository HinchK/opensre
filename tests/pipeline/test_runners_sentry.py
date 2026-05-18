from __future__ import annotations

import asyncio
import contextlib
import queue
import threading
from typing import cast

import pytest

from app.pipeline import runners
from app.state import AgentState
from app.utils import errors


def test_call_soon_threadsafe_on_closed_loop_raises_runtime_error() -> None:
    """Documents stdlib behaviour that _put / except / finally in astream guards against."""
    loop = asyncio.new_event_loop()
    loop.close()
    with pytest.raises(RuntimeError):
        loop.call_soon_threadsafe(lambda: None)


def test_astream_investigation_background_thread_safe_on_loop_close() -> None:
    """Except/finally sentinel path must not crash when the event loop has been closed."""

    def _simulate_run_pipeline(
        loop: asyncio.AbstractEventLoop,
        q: queue.Queue[object],
    ) -> None:
        try:
            raise ValueError("boom")
        except Exception as exc:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(q.put_nowait, exc)
        finally:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(q.put_nowait, None)

    q: queue.Queue[object] = queue.Queue()
    closed_loop = asyncio.new_event_loop()
    closed_loop.close()

    t = threading.Thread(target=_simulate_run_pipeline, args=(closed_loop, q), daemon=True)
    t.start()
    t.join(timeout=2)

    assert t.is_alive() is False
    assert q.empty()


def test_astream_investigation_is_noise_branch_thread_safe_on_loop_close() -> None:
    """The is_noise early-return path must guard call_soon_threadsafe the same way.

    Mirrors _run_pipeline: without suppress(RuntimeError) the background thread can raise when
    the consumer cancels and closes the loop before the noise sentinel is enqueued.
    """

    def _simulate_is_noise_branch(
        loop: asyncio.AbstractEventLoop,
        q: queue.Queue[object],
    ) -> None:
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(q.put_nowait, None)

    q: queue.Queue[object] = queue.Queue()
    closed_loop = asyncio.new_event_loop()
    closed_loop.close()

    t = threading.Thread(target=_simulate_is_noise_branch, args=(closed_loop, q), daemon=True)
    t.start()
    t.join(timeout=2)

    assert t.is_alive() is False
    assert q.empty()


async def _drive_astream_until_done(
    raw_alert: dict[str, object],
) -> list[object]:
    events: list[object] = []
    async for evt in runners.astream_investigation(raw_alert):
        events.append(evt)
    return events


def test_astream_investigation_is_noise_drains_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When extract_alert flags is_noise, the stream completes without error."""
    monkeypatch.setattr(runners, "init_sentry", lambda **_kw: None)

    import app.agent.context as context_module
    import app.agent.extract as extract_module

    monkeypatch.setattr(context_module, "resolve_integrations", lambda _state: {})
    monkeypatch.setattr(
        extract_module,
        "extract_alert",
        lambda _state: {
            "alert_name": "noise",
            "pipeline_name": "noise",
            "severity": "info",
            "is_noise": True,
        },
    )

    events = asyncio.run(_drive_astream_until_done({"alert": "noise"}))
    assert any(
        getattr(e, "node_name", None) == "extract_alert" for e in events
    ), "extract_alert events should be emitted before the noise early-return"


def test_run_chat_initializes_sentry_and_captures_unhandled_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentry_init_calls: list[None] = []
    captured_errors: list[BaseException] = []
    expected_error = RuntimeError("chat failed")

    def failing_chat(_state: AgentState) -> AgentState:
        raise expected_error

    def capture_stub(exc: BaseException, **_kwargs: object) -> None:
        captured_errors.append(exc)

    import app.pipeline.pipeline as pipeline_module

    monkeypatch.setattr(runners, "init_sentry", lambda **_kw: sentry_init_calls.append(None))
    monkeypatch.setattr(errors, "capture_exception", capture_stub)
    monkeypatch.setattr(pipeline_module, "run_chat", failing_chat)

    with pytest.raises(RuntimeError, match="chat failed"):
        runners.run_chat(cast(AgentState, {}))

    assert sentry_init_calls == [None]
    assert captured_errors == [expected_error]
