# 009-paid-fallback-violation — Auxiliary task fell back to paid OpenRouter model despite free-only config (#24029)

## Source
issue-24029

## Notes
User configured free-only but auxiliary chain bypassed the constraint. A single ERROR is sufficient to alert.

## Fixture
`errors.log` is a synthesized minimal log slice that exercises the
Hermes classifier on this failure mode. Lines and timestamps are
deterministic so the answer key remains stable across CI runs.
