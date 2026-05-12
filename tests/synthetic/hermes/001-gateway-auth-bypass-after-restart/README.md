# 001-gateway-auth-bypass-after-restart — Telegram polling conflict storm + gateway restart processes unauthorized message (#23778)

## Source
production-issue-23778

## Notes
Auth bypass occurred immediately after a polling conflict storm and a gateway restart. P0 security incident — the polling burst should fire first as warning_burst (early warning), and the subsequent ERROR from gateway.auth must surface as error_severity so the on-call is paged before the inverted auth state is observed.

## Fixture
`errors.log` is a synthesized minimal log slice that exercises the
Hermes classifier on this failure mode. Lines and timestamps are
deterministic so the answer key remains stable across CI runs.
