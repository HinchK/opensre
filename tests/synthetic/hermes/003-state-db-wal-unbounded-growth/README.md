# 003-state-db-wal-unbounded-growth — state.db WAL grows unbounded, PASSIVE checkpoint never truncates (#24034)

## Source
issue-24034

## Notes
WAL growth warnings escalate to a disk-full ERROR + traceback. Classifier must surface the early warning_burst so operators intervene before the disk fills.

## Fixture
`errors.log` is a synthesized minimal log slice that exercises the
Hermes classifier on this failure mode. Lines and timestamps are
deterministic so the answer key remains stable across CI runs.
