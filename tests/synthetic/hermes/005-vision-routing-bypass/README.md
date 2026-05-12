# 005-vision-routing-bypass — Non-vision model receives image_url, provider returns 400 (#23733, #24015)

## Source
issue-23733

## Notes
Vision routing failure produces a fingerprintable error_severity + traceback. AlarmDispatcher dedup ensures repeated image uploads to the same broken model produce one Telegram alert.

## Fixture
`errors.log` is a synthesized minimal log slice that exercises the
Hermes classifier on this failure mode. Lines and timestamps are
deterministic so the answer key remains stable across CI runs.
