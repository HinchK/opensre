"""Generate the 001-010 Hermes synthetic scenario fixtures.

Run from the repo root: ``python tests/synthetic/hermes/_generate_scenarios.py``.
The script is idempotent and lives in-tree so the fixtures can be
regenerated when log shapes change. It writes ``scenario.yml``,
``answer.yml``, ``README.md``, and ``errors.log`` for each scenario.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parent

Scenario = dict[str, str]

SCENARIOS: list[Scenario] = [
    {
        "id": "001-gateway-auth-bypass-after-restart",
        "title": "Telegram polling conflict storm + gateway restart processes unauthorized message (#23778)",
        "source": "production-issue-23778",
        "log": dedent(
            """\
            2026-05-11 16:04:12,001 WARNING gateway.platforms.telegram: Unauthorized user: 9876543210 on telegram
            2026-05-11 16:05:15,300 WARNING gateway.platforms.telegram: [Telegram] Telegram polling conflict (1/3), terminated by other getUpdates request
            2026-05-11 16:06:22,450 WARNING gateway.platforms.telegram: [Telegram] Telegram polling conflict (1/3), terminated by other getUpdates request
            2026-05-11 16:09:44,700 WARNING gateway.platforms.telegram: [Telegram] Telegram polling conflict (1/3), terminated by other getUpdates request
            2026-05-11 16:10:02,200 WARNING gateway.platforms.telegram: [Telegram] Telegram polling conflict (1/3), terminated by other getUpdates request
            2026-05-11 16:15:33,000 WARNING gateway.runner: Stopping gateway for restart...
            2026-05-11 16:15:44,000 WARNING gateway.runner: Starting Hermes Gateway...
            2026-05-11 16:15:45,000 WARNING gateway.platforms.telegram: Connected to Telegram (polling mode)
            2026-05-11 16:16:01,500 ERROR gateway.auth: auth bypass: inbound message from non-allowlisted user processed (user_id=9876543210)
            2026-05-11 16:30:03,800 WARNING gateway.platforms.telegram: Unauthorized user: 1234567890 (owner) on telegram
            """
        ),
        "classifier": {
            "warning_burst_threshold": 4,
            "warning_burst_window_s": 600,
        },
        "expected": [
            {"rule": "warning_burst", "logger": "gateway.platforms.telegram", "min_records": 4},
            {"rule": "error_severity", "severity": "high", "logger": "gateway.auth"},
        ],
        "counts": {"error_severity": "==1", "warning_burst": ">=1"},
        "readme_extra": (
            "Auth bypass occurred immediately after a polling conflict storm "
            "and a gateway restart. P0 security incident — the polling burst "
            "should fire first as warning_burst (early warning), and the "
            "subsequent ERROR from gateway.auth must surface as error_severity "
            "so the on-call is paged before the inverted auth state is observed."
        ),
    },
    {
        "id": "002-gateway-systemd-crash-loop",
        "title": "Gateway crash loop after upgrade (systemd Result=exit-code, Status=1)",
        "source": "gateway-troubleshooting-docs",
        "log": dedent(
            """\
            2026-05-11 18:00:01,000 CRITICAL gateway.runner: Gateway process exited with code 1
            2026-05-11 18:00:01,002 ERROR gateway.runner: Traceback (most recent call last):
              File "/opt/hermes/gateway/runner.py", line 412, in _bootstrap
                self._load_platforms()
              File "/opt/hermes/gateway/runner.py", line 367, in _load_platforms
                adapter = importlib.import_module(module_path)
            ModuleNotFoundError: No module named 'gateway.platforms.legacy_bridge'
            2026-05-11 18:00:11,000 CRITICAL gateway.runner: Gateway process exited with code 1
            2026-05-11 18:00:21,000 CRITICAL gateway.runner: Gateway process exited with code 1
            2026-05-11 18:00:31,000 CRITICAL gateway.runner: Gateway process exited with code 1
            2026-05-11 18:00:41,000 ERROR systemd: hermes-gateway.service: Failed with result 'exit-code'
            """
        ),
        "classifier": {},
        "expected": [
            {"rule": "traceback", "severity": "critical", "logger": "gateway.runner"},
            {"rule": "error_severity", "severity": "critical", "logger": "gateway.runner"},
        ],
        "counts": {"error_severity": ">=4", "traceback": ">=1"},
        "readme_extra": (
            "Repeated CRITICAL exits with the same fingerprint should produce "
            "one traceback incident and one error_severity per restart. The "
            "AlarmDispatcher's per-fingerprint cooldown collapses repeats; "
            "the classifier still emits them so audit trails are complete."
        ),
    },
    {
        "id": "003-state-db-wal-unbounded-growth",
        "title": "state.db WAL grows unbounded, PASSIVE checkpoint never truncates (#24034)",
        "source": "issue-24034",
        "log": dedent(
            """\
            2026-05-11 19:00:00,000 WARNING agent.session_store: state.db-wal size=512MB, last PASSIVE checkpoint busy
            2026-05-11 19:05:00,000 WARNING agent.session_store: state.db-wal size=648MB, last PASSIVE checkpoint busy
            2026-05-11 19:10:00,000 WARNING agent.session_store: state.db-wal size=784MB, last PASSIVE checkpoint busy
            2026-05-11 19:15:00,000 WARNING agent.session_store: state.db-wal size=920MB, last PASSIVE checkpoint busy
            2026-05-11 19:20:00,000 ERROR agent.session_store: sqlite3.OperationalError: database or disk is full
            2026-05-11 19:20:00,500 ERROR agent.session_store: Traceback (most recent call last):
              File "/opt/hermes/agent/session_store.py", line 188, in commit
                self._conn.commit()
            sqlite3.OperationalError: database or disk is full
            """
        ),
        "classifier": {"warning_burst_threshold": 3, "warning_burst_window_s": 900},
        "expected": [
            {"rule": "warning_burst", "logger": "agent.session_store"},
            {"rule": "error_severity", "severity": "high", "logger": "agent.session_store"},
            {"rule": "traceback", "logger": "agent.session_store"},
        ],
        "counts": {"warning_burst": ">=1", "error_severity": ">=1", "traceback": ">=1"},
        "readme_extra": (
            "WAL growth warnings escalate to a disk-full ERROR + traceback. "
            "Classifier must surface the early warning_burst so operators "
            "intervene before the disk fills."
        ),
    },
    {
        "id": "004-context-length-overflow",
        "title": "Oversized prompt after lower-context model switch (#23767, #24000, #24080)",
        "source": "issue-23767",
        "log": dedent(
            """\
            2026-05-11 12:00:01,100 WARNING agent.context: estimated tokens=180000 > model.context_length=32768
            2026-05-11 12:00:01,500 ERROR agent.run_agent: provider returned 400: prompt exceeds model maximum context length of 32768 tokens
            """
        ),
        "classifier": {},
        "expected": [
            {"rule": "error_severity", "severity": "high", "logger": "agent.run_agent"},
        ],
        "counts": {"error_severity": "==1"},
        "readme_extra": (
            "Single ERROR captures the provider 400. The preceding WARNING "
            "alone is below burst threshold so warning_burst correctly does "
            "not fire (one-shot warning is noise without a burst pattern)."
        ),
    },
    {
        "id": "005-vision-routing-bypass",
        "title": "Non-vision model receives image_url, provider returns 400 (#23733, #24015)",
        "source": "issue-23733",
        "log": dedent(
            """\
            2026-05-11 09:00:00,100 ERROR agent.run_agent: provider returned 400: model 'qwen2.5-coder:7b' does not support image input (image_url passed in messages[3].content)
            2026-05-11 09:00:00,200 ERROR agent.run_agent: Traceback (most recent call last):
              File "/opt/hermes/agent/run_agent.py", line 740, in _call_llm
                response = await client.chat.completions.create(**kwargs)
            openai.BadRequestError: 400 Bad Request: model does not support image input
            """
        ),
        "classifier": {},
        "expected": [
            {"rule": "error_severity", "severity": "high", "logger": "agent.run_agent"},
            {"rule": "traceback", "logger": "agent.run_agent"},
        ],
        "counts": {"error_severity": ">=1", "traceback": ">=1"},
        "readme_extra": (
            "Vision routing failure produces a fingerprintable error_severity "
            "+ traceback. AlarmDispatcher dedup ensures repeated image "
            "uploads to the same broken model produce one Telegram alert."
        ),
    },
    {
        "id": "006-adapter-attribute-error",
        "title": "LINE adapter AttributeError on init (#23728)",
        "source": "issue-23728",
        "log": dedent(
            """\
            2026-05-11 10:45:18,000 ERROR gateway.platforms.line: adapter init failed: 'LineAdapter' object has no attribute 'create_source'
            2026-05-11 10:45:18,100 ERROR gateway.platforms.line: Traceback (most recent call last):
              File "/opt/hermes/gateway/platforms/line.py", line 88, in start
                self.source = self.create_source()
            AttributeError: 'LineAdapter' object has no attribute 'create_source'. Did you mean 'build_source'?
            """
        ),
        "classifier": {},
        "expected": [
            {"rule": "error_severity", "severity": "high", "logger": "gateway.platforms.line"},
            {"rule": "traceback", "logger": "gateway.platforms.line"},
        ],
        "counts": {"error_severity": ">=1", "traceback": ">=1"},
        "readme_extra": (
            "Straight AttributeError + traceback. Verifies the classifier "
            "correctly attaches continuation frames to the parent record."
        ),
    },
    {
        "id": "007-feishu-misroute-burst",
        "title": "Feishu group replies misrouted to sender's DM (#23698, #23732)",
        "source": "issue-23698",
        "log": dedent(
            """\
            2026-05-11 09:37:01,000 WARNING gateway.platforms.feishu: reply route fallback: message_id missing, defaulting to home channel
            2026-05-11 09:37:18,000 WARNING gateway.platforms.feishu: reply route fallback: message_id missing, defaulting to home channel
            2026-05-11 09:37:42,000 WARNING gateway.platforms.feishu: reply route fallback: message_id missing, defaulting to home channel
            2026-05-11 09:38:05,000 WARNING gateway.platforms.feishu: reply route fallback: message_id missing, defaulting to home channel
            2026-05-11 09:38:30,000 WARNING gateway.platforms.feishu: reply route fallback: message_id missing, defaulting to home channel
            """
        ),
        "classifier": {"warning_burst_threshold": 4, "warning_burst_window_s": 120},
        "expected": [
            {"rule": "warning_burst", "logger": "gateway.platforms.feishu", "min_records": 4},
        ],
        "counts": {"warning_burst": ">=1", "error_severity": "==0"},
        "readme_extra": (
            "Repeated WARNING-only failures form a burst. MEDIUM severity → "
            "notify-only delivery, no investigation triggered."
        ),
    },
    {
        "id": "008-pid-lock-zombie",
        "title": "macOS stale PID lock — system process occupies same PID (#24067)",
        "source": "issue-24067",
        "log": dedent(
            """\
            2026-05-12 00:14:54,000 ERROR gateway.runner: refusing to start: PID lock 41827 appears active (no /proc on macOS, falling back to kill -0)
            2026-05-12 00:14:54,100 ERROR gateway.runner: Traceback (most recent call last):
              File "/opt/hermes/gateway/runner.py", line 121, in acquire_lock
                raise RuntimeError(f"stale PID {pid} appears live; remove {self.lock_path} manually")
            RuntimeError: stale PID 41827 appears live; remove /Users/x/.hermes/gateway.pid manually
            """
        ),
        "classifier": {},
        "expected": [
            {"rule": "error_severity", "severity": "high", "logger": "gateway.runner"},
            {"rule": "traceback", "logger": "gateway.runner"},
        ],
        "counts": {"error_severity": ">=1", "traceback": ">=1"},
        "readme_extra": (
            "macOS-specific failure mode — the classifier should not treat the "
            "kernel-version-specific path string as a continuation."
        ),
    },
    {
        "id": "009-paid-fallback-violation",
        "title": "Auxiliary task fell back to paid OpenRouter model despite free-only config (#24029)",
        "source": "issue-24029",
        "log": dedent(
            """\
            2026-05-11 22:00:00,000 WARNING agent.aux_fallback: free model 'openrouter/free-aux' returned 429; falling back to 'openrouter/paid-aux' (rate=$0.50/Mtok)
            2026-05-11 22:00:01,000 ERROR agent.aux_fallback: auxiliary fallback chose paid model 'openrouter/paid-aux' while OPENROUTER_FREE_ONLY=1 — request was not free-only
            """
        ),
        "classifier": {},
        "expected": [
            {"rule": "error_severity", "severity": "high", "logger": "agent.aux_fallback"},
        ],
        "counts": {"error_severity": "==1"},
        "readme_extra": (
            "User configured free-only but auxiliary chain bypassed the "
            "constraint. A single ERROR is sufficient to alert."
        ),
    },
    {
        "id": "010-cron-tick-overlap",
        "title": "Cron tick lock contention + weekly_maintenance hardcoded path (#24034, #24035)",
        "source": "issues-24034-24035",
        "log": dedent(
            """\
            2026-05-11 22:18:33,000 WARNING cron.scheduler: tick skipped: .tick.lock held by pid=2914 for 47.2s
            2026-05-11 22:18:36,000 WARNING cron.scheduler: tick skipped: .tick.lock held by pid=2914 for 50.1s
            2026-05-11 22:18:39,000 WARNING cron.scheduler: tick skipped: .tick.lock held by pid=2914 for 53.0s
            2026-05-11 22:18:42,000 WARNING cron.scheduler: tick skipped: .tick.lock held by pid=2914 for 55.9s
            2026-05-11 22:18:45,000 ERROR cron.weekly_maintenance: hardcoded path /home/ubuntu/.hermes not writable; profile $HERMES_HOME ignored
            """
        ),
        "classifier": {"warning_burst_threshold": 3, "warning_burst_window_s": 60},
        "expected": [
            {"rule": "warning_burst", "logger": "cron.scheduler"},
            {"rule": "error_severity", "severity": "high", "logger": "cron.weekly_maintenance"},
        ],
        "counts": {"warning_burst": ">=1", "error_severity": ">=1"},
        "readme_extra": (
            "Tick contention surfaces as warning_burst, profile-path bug as "
            "error_severity from a different logger. Two distinct "
            "fingerprints — both should reach Telegram."
        ),
    },
]


def render_scenario_yml(scenario: Scenario) -> str:
    lines = [
        f'scenario_id: "{scenario["id"]}"',
        f'title: "{scenario["title"]}"',
        f'source: "{scenario["source"]}"',
        'log_file: "errors.log"',
    ]
    classifier = scenario.get("classifier") or {}
    if classifier:
        lines.append("classifier:")
        for key, value in classifier.items():
            lines.append(f"  {key}: {value}")
    return "\n".join(lines) + "\n"


def render_answer_yml(scenario: Scenario) -> str:
    out = ["expected_incidents:"]
    for entry in scenario["expected"]:
        out.append(f'  - rule: "{entry["rule"]}"')
        if "severity" in entry:
            out.append(f'    severity: "{entry["severity"]}"')
        if "logger" in entry:
            out.append(f'    logger: "{entry["logger"]}"')
        if "title_contains" in entry:
            out.append(f'    title_contains: "{entry["title_contains"]}"')
        if "min_records" in entry:
            out.append(f"    min_records: {entry['min_records']}")
    out.append("")
    out.append("expected_incident_count:")
    for rule, expr in scenario["counts"].items():
        out.append(f'  {rule}: "{expr}"')
    return "\n".join(out) + "\n"


def render_readme(scenario: Scenario) -> str:
    return dedent(
        f"""\
        # {scenario["id"]} — {scenario["title"]}

        ## Source
        {scenario["source"]}

        ## Notes
        {scenario["readme_extra"]}

        ## Fixture
        `errors.log` is a synthesized minimal log slice that exercises the
        Hermes classifier on this failure mode. Lines and timestamps are
        deterministic so the answer key remains stable across CI runs.
        """
    )


def main() -> None:
    for scenario in SCENARIOS:
        scenario_dir = ROOT / scenario["id"]
        scenario_dir.mkdir(parents=True, exist_ok=True)
        (scenario_dir / "scenario.yml").write_text(render_scenario_yml(scenario), encoding="utf-8")
        (scenario_dir / "answer.yml").write_text(render_answer_yml(scenario), encoding="utf-8")
        (scenario_dir / "README.md").write_text(render_readme(scenario), encoding="utf-8")
        (scenario_dir / "errors.log").write_text(scenario["log"], encoding="utf-8")
        print(f"wrote {scenario_dir}")


if __name__ == "__main__":
    main()
