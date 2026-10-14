# Phase 01 review — deterministic fraud decisioning

**Status: PASS.** The Phase 1 decision path is coherent, independently validated, and stays within the master reference. This review closes Phase 1 only.

## 1. What was built?

CP01 defined immutable, validated user, device, transaction, payment attempt, risk signal, and decision snapshots. CP02 added three pure, three-state count rules that retain attributable signal evidence. CP03 separated rule-set evaluation from a versioned policy that composes one action. CP04 mapped complete `DecisionRecord`s to an insert-only PostgreSQL audit schema. CP05 exposed the path through a validated HTTP Decision API with atomic request idempotency, readiness, and explicit database failure behavior. In order: caller-provided facts → rules → policy → PostgreSQL audit and idempotency → HTTP response. No Phase 1 decision requires Redis, Kafka, ML, or an LLM.

## 2. What changed from the master plan?

No material architectural deviation. SQLAlchemy Core mapping, PostgreSQL-backed HTTP idempotency, a conservative demonstration policy, and three example rules elaborate the prescribed deterministic domain and PostgreSQL authority. The master reference's generic reproducibility metadata is populated only for actual Phase 1 producers; no fictitious model or feature versions were added.

## 3. Why did it change?

No material architectural deviation. The elaborations above establish precise transactional and historical semantics for the planned API.

## 4. What failed?

**Design/correctness discoveries:** CP03 clarified that a rule implementation version does not identify deployed thresholds, source, or membership. Those belong to the rule-set version; policy composition has its own version. CP05 made request identity and database availability explicit, so a failed write cannot masquerade as a decision.

**Tooling/test issues:** CP03 initially had import-order, line-length, and formatting failures in tests; CP04's first integration run exposed a test-cleanup transaction error fixed with a savepoint; CP05 corrected an unformatted test file. Each affected check passed after correction. These were not unresolved production defects. CP06's first smoke command used a missing bare `python` executable; rerunning via `uv run --locked python` passed.

## 5. What was learned?

- **Transaction and PaymentAttempt:** A transaction is the commercial action; a payment attempt is one effort to fund it. Several attempts can belong to one transaction, and fraud reasoning must preserve which attempt was evaluated. A device is an observation that may appear with several users, not an owned child of one user.
- **RiskSignal, RuleEvaluation, and Decision:** A risk signal is a typed, time-stamped observation with a source. A rule evaluation interprets one condition and records its status, reason/diagnostic, and exact evidence. A decision is the final historical system judgment after policy composition. They cannot be interchanged without losing provenance.
- **Three states:** `MATCHED` means valid evidence meets the condition; `NOT_MATCHED` means valid evidence was examined and did not; `INDETERMINATE` means evidence is missing, ambiguous, or the wrong type. Missing evidence is not evidence of safety. The current policy generally maps uncertainty to `REVIEW`, except when a matched `BLOCK` already determines the outcome.
- **Rule, rule set, policy:** A rule version identifies implementation semantics. A rule-set version identifies the published combination of rule membership, thresholds, and expected sources. A policy version identifies composition and conflict behavior. These distinct identities, stored with the evaluations and decision, explain which behavior produced a historical result. Versions are publication discipline today; past configuration/code is not yet historically loadable from a registry. The persisted facts and evaluations still allow an old decision to be inspected.
- **Deterministic core:** Given equal context, rule configuration, and policy inputs, evaluation and composition are deterministic. UUID and current UTC time are generated at the application boundary and supplied to decision construction, keeping the core free of clocks and random IDs.
- **PostgreSQL authority:** A successful decision cannot live only in process memory: it must survive process loss and be reconstructible for audit. One database transaction commits the idempotency claim, shared facts, context signals, ordered evaluations and evidence, ordered reasons, and final decision. Any failure rolls the transaction back; HTTP success follows commit.
- **HTTP idempotency:** `Idempotency-Key` names one logical HTTP request and maps its normalized request fingerprint to a committed decision. `decision_id` identifies the historical judgment, `transaction_id` the commercial action, and `payment_id` one funding attempt. `event_id` identifies a future event delivery and has no Phase 1 HTTP role. Repeated delivery with the same key and semantic request returns the same decision; changing the request under that key returns 409. It does not create a second logical decision.
- **Business uncertainty and infrastructure failure:** A missing fraud signal produces `INDETERMINATE`, which policy may validly turn into a persisted `REVIEW`. PostgreSQL unavailability prevents authoritative decision truth, so the API returns 503, never a synthetic `ALLOW`.
- **Liveness and readiness:** `/health/live` reports process responsiveness. `/health/ready` checks PostgreSQL connectivity and decision schema capability. Thus live can remain 200 while ready becomes 503 when the required database fails.

## 6. What metrics were observed?

CP06 measured 146 pure/offline tests and 7 real PostgreSQL integration tests passing. PostgreSQL has 11 Phase 1 audit/idempotency tables across two migration revisions (`09fc42332bec`, `64d97b805b13`); Alembic reports the latter as head and no drift. The five Compose services were healthy. Container HTTP observed Decision live/ready and Investigator live at 200; first payment POST at 200 with `replayed=false`, identical retry at 200 with the same decision and `replayed=true`, and changed request under the same key at 409. CP05 measured database outage behavior: live 200, ready 503, POST 503; after restoration ready 200 and POST 200. Phase 1 has no throughput or latency benchmark.

## 7. What technical debt was introduced?

**Intentional deferred work:** Rule-set publication/history loading remains manual; HTTP idempotency claims have no retention/cleanup policy; online feature computation, Kafka application integration, event deduplication/replay, and broader observability belong to later scopes. These are boundaries, not current correctness defects.

**Undesirable debt:** The locked Starlette/AnyIO combination emits one upstream deprecation warning during tests. It does not affect this checkpoint's behavior; revisit when dependency maintenance justifies it. No known Phase 1 correctness compromise remains.

## 8. Is Phase 2 still the correct next phase?

Yes. Phase 1 receives risk signals directly from the caller. The next question is how online signals arise and remain correct under duplicates and replay. The master reference's Phase 2 addresses event-driven feature processing and derived Redis state under at-least-once delivery. Phase 1 found no reason to reorder this sequence. Phase 2 does not introduce ML or LLM decisioning.

## 9. Does the master plan need an ADR/update?

No. PostgreSQL HTTP idempotency reinforces the existing authority and at-least-once principles. Distinct rule/rule-set/policy versions make reproducibility precise. SQLAlchemy Core is a mapping choice that leaves the domain independent. None changes a master architectural invariant or requires an ADR now.

## Phase 1 Gate

- **Incoming facts:** `UserAccount` identifies the user; `Transaction` identifies that user's commercial action and amount; `PaymentAttempt` identifies one attempt for that transaction; `Device` is an observed device without exclusive ownership; `RiskSignal` supplies a typed, sourced, time-stamped observation. `DecisionContext` checks the available user/transaction/payment references.
- **Money:** Nonnegative integer minor units and normalized three-letter currency codes avoid binary floating-point money error. No exchange calculation is implied.
- **Missing versus safe:** A rule can say `NOT_MATCHED` only after valid evidence was examined. Missing, ambiguous, or mistyped evidence is `INDETERMINATE`, not zero risk.
- **Why policy decides:** A rule interprets one condition and may recommend an action; policy combines all evaluations, uncertainty, and conflicts into one decision.
- **Old configuration:** Stored rule identities/versions in ordered evaluations, plus decision rule-set and policy identities/versions, identify the behavior that produced the result. The complete input and evidence are stored. A publication registry and historical loader for old deployed configurations do not yet exist.
- **Authority:** PostgreSQL owns Phase 1 recorded facts, audit, and HTTP idempotency. Redis owns no decision truth; Kafka is not on the decision path and does not provide an event identity for these requests.
- **Atomic contents:** One transaction holds the key/fingerprint/decision claim and the complete `DecisionRecord`: related facts, devices, all context signals, rule-set evaluation, ordered per-rule statuses/diagnostics/evidence, final decision and reasons.
- **Database failure:** Without a durable commit, an `ALLOW` or other action cannot be asserted as a successful decision. The API reports 503 for database unavailability.
- **Idempotency-Key:** A caller-supplied logical HTTP request identity. Equal normalized requests replay the committed decision; changed content under the key conflicts. It is distinct from decision, transaction, payment, and future event IDs.
- **Live versus ready:** The process can answer `/health/live` while database connectivity or schema is unavailable, so `/health/ready` returns 503.

## Architecture invariants review

- [x] Decisions are immutable historical outputs (frozen models and insert-only repository).
- [x] Evidence remains attributable (source/time/value, ordered evaluation evidence, and reason codes).
- [x] Rules are deterministic and perform no I/O.
- [x] Policy consumes evaluations, not raw signals.
- [x] Rule, rule-set, and policy versions have distinct semantics.
- [x] PostgreSQL is authoritative for recorded Phase 1 truth.
- [x] Redis is not on the decision path.
- [x] Kafka is not on the decision path.
- [x] LLMs are absent from the decision path.
- [x] ML is absent from Phase 1.
- [x] HTTP retries do not create duplicate logical decisions (including concurrent same-key claims).
- [x] Database failure does not become a business `ALLOW`.
- [x] Investigator API remains independent and liveness-only.

**Closure:** PASS. CP06 reused CP05's database outage/recovery evidence because the relevant code was unchanged and current validation did not contradict it. No production change or ADR was needed.
