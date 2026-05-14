from __future__ import annotations

import time

import pytest
import questionary
from prompt_toolkit.input.defaults import create_pipe_input  # type: ignore[import-not-found]
from prompt_toolkit.output import DummyOutput  # type: ignore[import-not-found]

from app.cli.support.prompt_support import (
    _last_ctrl_c,
    _sigint_delegate,
    handle_ctrl_c_press,
    handle_sigint_for_cli,
    install_questionary_ctrl_c_double_exit,
    install_questionary_escape_cancel,
    set_sigint_delegate,
)


def test_install_questionary_escape_cancel_is_idempotent() -> None:
    install_questionary_escape_cancel()
    first = questionary.select
    install_questionary_escape_cancel()
    assert questionary.select is first


def test_stock_questionary_select_escape_cancels() -> None:
    install_questionary_escape_cancel()
    with create_pipe_input() as pipe_input:
        q = questionary.select(
            "Pick",
            choices=["a", "b"],
            input=pipe_input,
            output=DummyOutput(),
        )
        pipe_input.send_bytes(b"\x1b")
        app = q.application
        app.input = pipe_input
        app.output = DummyOutput()
        assert app.run() is None


def test_stock_questionary_confirm_escape_cancels() -> None:
    """Verify that pressing Escape cancels a confirm prompt (Issue #1117).

    Sends the Escape byte (\\x1b) to a questionary.confirm application
    and asserts that it returns None instead of hanging.
    """
    install_questionary_escape_cancel()
    with create_pipe_input() as pipe_input:
        q = questionary.confirm(
            "Are you sure?",
            input=pipe_input,
            output=DummyOutput(),
        )
        pipe_input.send_bytes(b"\x1b")
        app = q.application
        app.input = pipe_input
        app.output = DummyOutput()
        assert app.run() is None


def test_stock_questionary_text_escape_cancels() -> None:
    """Verify that pressing Escape cancels a text input prompt (Issue #1117).

    Sends the Escape byte (\\x1b) to a questionary.text application
    and asserts that it returns None.
    """
    install_questionary_escape_cancel()
    with create_pipe_input() as pipe_input:
        q = questionary.text(
            "Name",
            input=pipe_input,
            output=DummyOutput(),
        )
        pipe_input.send_bytes(b"\x1b")
        app = q.application
        app.input = pipe_input
        app.output = DummyOutput()
        assert app.run() is None


def test_stock_questionary_path_escape_cancels() -> None:
    """Verify that pressing Escape cancels a path selection prompt (Issue #1117).

    Sends the Escape byte (\\x1b) to a questionary.path application
    and asserts that it returns None.
    """
    install_questionary_escape_cancel()
    with create_pipe_input() as pipe_input:
        q = questionary.path(
            "Path",
            input=pipe_input,
            output=DummyOutput(),
        )
        pipe_input.send_bytes(b"\x1b")
        app = q.application
        app.input = pipe_input
        app.output = DummyOutput()
        assert app.run() is None


def test_install_questionary_ctrl_c_double_exit_is_idempotent() -> None:
    install_questionary_ctrl_c_double_exit()
    first = questionary.select
    install_questionary_ctrl_c_double_exit()
    assert questionary.select is first


def test_ctrl_c_first_press_shows_hint_and_reprompts(capsys) -> None:
    """First Ctrl+C prints the hint and re-displays the prompt; Enter then submits."""
    _last_ctrl_c[0] = None
    install_questionary_ctrl_c_double_exit()
    with create_pipe_input() as pipe_input:
        q = questionary.select(
            "Pick",
            choices=["a", "b"],
            input=pipe_input,
            output=DummyOutput(),
        )
        # Ctrl+C cancels the first run; Enter submits the re-displayed prompt.
        pipe_input.send_bytes(b"\x03\r")
        result = q.ask()
    assert "(Press Ctrl+C again to exit)" in capsys.readouterr().out
    # After the hint the prompt was re-run and "a" was selected (first choice).
    assert result == "a"


def test_ctrl_c_second_press_exits(capsys) -> None:
    # Simulate a previous Ctrl+C just now so the second press fires immediately.
    _last_ctrl_c[0] = time.monotonic()
    with pytest.raises(SystemExit) as exc_info:
        handle_ctrl_c_press()
    assert exc_info.value.code == 0
    assert "Goodbye" in capsys.readouterr().out


def test_ctrl_c_hint_resets_after_window(capsys) -> None:
    # A press older than the exit window should show the hint again, not exit.
    _last_ctrl_c[0] = None  # effectively "long ago"
    handle_ctrl_c_press()
    out = capsys.readouterr().out
    assert "(Press Ctrl+C again to exit)" in out


def test_handle_sigint_for_cli_uses_delegate_when_handled(capsys) -> None:
    _last_ctrl_c[0] = None
    set_sigint_delegate(lambda: True)
    try:
        handle_sigint_for_cli()
    finally:
        set_sigint_delegate(None)
    assert capsys.readouterr().out == ""
    assert _last_ctrl_c[0] is None


def test_handle_sigint_for_cli_falls_back_when_delegate_not_handled(capsys) -> None:
    _last_ctrl_c[0] = None
    set_sigint_delegate(lambda: False)
    try:
        handle_sigint_for_cli()
    finally:
        set_sigint_delegate(None)
    out = capsys.readouterr().out
    assert "(Press Ctrl+C again to exit)" in out


def test_handle_sigint_for_cli_falls_back_when_delegate_errors(capsys) -> None:
    _last_ctrl_c[0] = None

    def _boom() -> bool:
        raise RuntimeError("boom")

    set_sigint_delegate(_boom)
    try:
        handle_sigint_for_cli()
    finally:
        set_sigint_delegate(None)
    out = capsys.readouterr().out
    assert "(Press Ctrl+C again to exit)" in out


def test_sigint_delegate_starts_cleared() -> None:
    set_sigint_delegate(None)
    assert _sigint_delegate[0] is None


def test_questionary_ask_inside_running_event_loop_does_not_raise() -> None:
    """q.ask() called from within a running asyncio event loop must not raise.

    Regression test for Sentry issue #1650: asyncio.run() cannot be called
    from a running event loop — triggered when questionary prompts are shown
    inside the async REPL dispatch path.
    """
    import asyncio

    _last_ctrl_c[0] = None
    install_questionary_ctrl_c_double_exit()

    async def _run() -> object:
        with create_pipe_input() as pipe_input:
            q = questionary.select(
                "Pick",
                choices=["a", "b"],
                input=pipe_input,
                output=DummyOutput(),
            )
            pipe_input.send_bytes(b"\r")
            return q.ask()

    result = asyncio.run(_run())
    assert result == "a"
