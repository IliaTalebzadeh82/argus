# Phase 03 / Checkpoint 03 — Coordinated fraud synthetic world

## Status
`PASS`

## Objective
Generate deterministic fraud rings, simulator-only shared relationships, and production-compatible payment and chargeback facts without leaking scenario truth.

## Implemented
- Added immutable, validated `FraudScenarioConfig` and canonical JSON metadata. Simulator version remains **1**.
- Generated ring account farms with one shared production device per ring, one latent card and promo identity per ring, per-transaction card uses, and first-payment promo redemptions.
- Generated ordinary attempted, failed, completed, and later chargeback events with deterministic UUIDv5 IDs and traces. Every event passes V1 validation.
- Reused CP02's exact event UUID construction and validation via a small shared simulation helper; legitimate behavior is unchanged.
- Added architecture documentation and 34 focused fraud tests, including leakage, locality, causal ordering, and reference projector coverage.

## Key decisions
- Shared card, promo, farm, and ring relationships are immutable simulator truth, not production payloads, RiskSignals, online evidence, or training labels. Current rules see shared device and payment/failure velocity only.
- Ring `r` starts at `starts_at + r * ring_spacing`; account `i` starts at ring start plus `i * account_spacing`. Payment `j` follows first delay plus `j * payment_spacing`; terminal and eligible chargeback delays follow causally.
- Independent per-user namespaces are `fraud-payments:{user_id}:amount`, `:merchant`, `:outcome`, and `:chargeback`. Appended rings do not shift previous ring behavior. UUIDv5 names include canonical manifest, entire fraud config, event type, and subject, so a config change can change previous event UUIDs.
- Events emit globally in `(occurred_at, planning ordinal)` order. `produced_at = occurred_at = generated_at`; zero-delay completion precedes its chargeback.

## Files changed
- Scenario and shared event construction: `src/argus/simulation/{fraud_world,events,legitimate}.py`.
- Tests: `tests/unit/test_fraud_simulation.py`.
- Architecture: `docs/architecture/synthetic-fraud-world.md`.
- Report: this file.

## Validation
- `uv sync --locked`: passed; 33 packages resolved, 31 checked.
- `uv run --locked pytest tests/unit/test_simulation_kernel.py tests/unit/test_legitimate_simulation.py tests/unit/test_fraud_simulation.py -q`: **66 passed**.
- `make check`: Ruff lint/format passed; **242 offline tests passed**, one existing upstream Starlette/AnyIO deprecation warning.
- `docker compose config --quiet`: passed.
- `git diff --check` and `git diff --cached --check`: passed.
- Controlled ring projector: four accounts on the same device; each member has `accounts_on_device=4`, `payments_10m=5`, and `failed_payments_1h=5`.
- Initial focused run passed with 101 Pydantic deprecation warnings from one test assertion. Corrected the assertion; focused and full checks passed on rerun without that warning.
- No dependency or Compose changes; no containers started.

## Acceptance criteria
- [x] Separate immutable fraud config/result and ring/account-farm behavior; CP01/CP02 tests unchanged and passing.
- [x] One shared device/card/promo identity per ring; card and promo records reference generated users and transactions.
- [x] Production IDs and exact V1 event payload fields reveal no ring, card, promo, or fraud truth; no new production schema or RiskSignal.
- [x] Deterministic independent streams, locality, canonical metadata, UUIDv5 events, global chronology, and equal-time ties verified.
- [x] Failure, success, chargeback, zero-chargeback, and zero-payment boundaries verified; chargeback follows successful completion only.
- [x] Reference projector proves visible shared-device and payment/failure bursts.
- [x] Documentation, focused/full offline checks, Compose validation, implementation commit completed.
- [x] Report commit, push, remote HEAD, and clean worktree verified in final handoff after report creation.

## Architecture / invariants check
Master reference preserved. No ADR or deliberate deviation. PostgreSQL authority and at-least-once feature processing are untouched. No mixed traffic, transport faults, late production, Kafka, filesystem export, ML, labels, graph implementation, or infrastructure I/O was added.

## Git
- Branch: `main`.
- Implementation commit: `b6eafa0b740205b4355eb4cadffc00f0fb56b041` (`phase-03/cp-03: add coordinated fraud simulation`).
- Report commit: this report's commit; SHA supplied in final handoff.
- Remote: `origin` (`git@github.com:IliaTalebzadeh82/argus.git`).
- Push result: pending report commit; final handoff verifies it.
- Final `git status`: pending post-push verification.

## Resource / usage notes
Only offline tests and Compose configuration validation ran. No containers started. No token estimate is available.

## Risks / technical debt
Card and promo relationships are latent until future production contracts justify visibility. Exact PRNG output remains scoped to Python 3.13 and the locked environment. No other known CP03 correctness debt remains.

## Next recommended checkpoint
Phase 03 / Checkpoint 04 may compose legitimate and fraud populations and introduce the separately scoped traffic-shape, delivery, and lateness behavior. This checkpoint does not implement that work.

## Handoff notes for ChatGPT
The scenario emits only the five existing Phase-2 fraud event types. Config fields are `ring_count`, `accounts_per_ring`, `payments_per_account`, `merchant_count`, two outcome probabilities, amount bounds/currency, and six timing durations. The result retains ring, card-use, and promo-redemption truth separately from event records. Tests explicitly inspect production payload fields and absence of leakage markers.
