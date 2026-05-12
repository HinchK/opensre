# 007-feishu-misroute-burst — Feishu group replies misrouted to sender's DM (#23698, #23732)

## Source
issue-23698

## Notes
Repeated WARNING-only failures form a burst. MEDIUM severity → notify-only delivery, no investigation triggered.

## Fixture
`errors.log` is a synthesized minimal log slice that exercises the
Hermes classifier on this failure mode. Lines and timestamps are
deterministic so the answer key remains stable across CI runs.
