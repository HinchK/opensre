# 006-adapter-attribute-error — LINE adapter AttributeError on init (#23728)

## Source
issue-23728

## Notes
Straight AttributeError + traceback. Verifies the classifier correctly attaches continuation frames to the parent record.

## Fixture
`errors.log` is a synthesized minimal log slice that exercises the
Hermes classifier on this failure mode. Lines and timestamps are
deterministic so the answer key remains stable across CI runs.
