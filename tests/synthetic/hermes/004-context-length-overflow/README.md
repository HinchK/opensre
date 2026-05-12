# 004-context-length-overflow — Oversized prompt after lower-context model switch (#23767, #24000, #24080)

## Source
issue-23767

## Notes
Single ERROR captures the provider 400. The preceding WARNING alone is below burst threshold so warning_burst correctly does not fire (one-shot warning is noise without a burst pattern).

## Fixture
`errors.log` is a synthesized minimal log slice that exercises the
Hermes classifier on this failure mode. Lines and timestamps are
deterministic so the answer key remains stable across CI runs.
