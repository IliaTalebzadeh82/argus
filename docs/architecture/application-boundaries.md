# Application boundaries (Phase 00 / Checkpoint 03)

The Decision API serves the synchronous deterministic Phase-1 decision path. LLM inference must never become required for Decision API
availability. The Investigator API will serve human investigation workflows and
access to asynchronously produced AI assistance.

Both processes serve `GET /health/live`. Decision API additionally serves
`GET /health/ready` and `POST /v1/decisions/payment`. Their service identity
is fixed in each application; `ARGUS_HOST`, `ARGUS_PORT`, and `ARGUS_LOG_LEVEL`
configure binding and logging. Host defaults are `127.0.0.1:8001` and
`127.0.0.1:8002`; Compose binds each process to `0.0.0.0` inside its container
and publishes those ports on host loopback only.

Current dependency graph:

```text
Decision API     -> PostgreSQL
Investigator API -> no datastore, broker, or LLM dependency
```

PostgreSQL is required for authoritative decision recording. Decision API
readiness checks database connectivity and schema capability; process liveness
remains database-independent. Investigator API remains liveness-only.
