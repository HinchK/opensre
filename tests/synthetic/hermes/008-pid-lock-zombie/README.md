# 008-pid-lock-zombie — macOS stale PID lock — system process occupies same PID (#24067)

## Source
issue-24067

## Notes
macOS-specific failure mode — the classifier should not treat the kernel-version-specific path string as a continuation.

## Fixture
`errors.log` is a synthesized minimal log slice that exercises the
Hermes classifier on this failure mode. Lines and timestamps are
deterministic so the answer key remains stable across CI runs.
