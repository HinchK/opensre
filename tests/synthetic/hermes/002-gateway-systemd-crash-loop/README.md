# 002-gateway-systemd-crash-loop — Gateway crash loop after upgrade (systemd Result=exit-code, Status=1)

## Source
gateway-troubleshooting-docs

## Notes
Repeated CRITICAL exits with the same fingerprint should produce one traceback incident and one error_severity per restart. The AlarmDispatcher's per-fingerprint cooldown collapses repeats; the classifier still emits them so audit trails are complete.

## Fixture
`errors.log` is a synthesized minimal log slice that exercises the
Hermes classifier on this failure mode. Lines and timestamps are
deterministic so the answer key remains stable across CI runs.
