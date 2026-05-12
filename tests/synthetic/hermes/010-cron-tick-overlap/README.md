# 010-cron-tick-overlap — Cron tick lock contention + weekly_maintenance hardcoded path (#24034, #24035)

## Source
issues-24034-24035

## Notes
Tick contention surfaces as warning_burst, profile-path bug as error_severity from a different logger. Two distinct fingerprints — both should reach Telegram.

## Fixture
`errors.log` is a synthesized minimal log slice that exercises the
Hermes classifier on this failure mode. Lines and timestamps are
deterministic so the answer key remains stable across CI runs.
