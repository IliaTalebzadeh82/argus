# Application boundaries (Phase 00 / Checkpoint 03)

The Decision API is the future low-latency synchronous deterministic/predictive
decision path. LLM inference must never become required for Decision API
availability. The Investigator API will serve human investigation workflows and
access to asynchronously produced AI assistance.

Both processes currently serve only `GET /health/live`. Their service identity
is fixed in each application; `ARGUS_HOST`, `ARGUS_PORT`, and `ARGUS_LOG_LEVEL`
configure binding and logging. Host defaults are `127.0.0.1:8001` and
`127.0.0.1:8002`; Compose binds each process to `0.0.0.0` inside its container
and publishes those ports on host loopback only.

Current dependency graph:

```text
Decision API     -> no datastore or broker dependency
Investigator API -> no datastore, broker, or LLM dependency
```

PostgreSQL, Redis, and Kafka run beside these services, but network proximity
does not create an architectural dependency. Wiring them now would imply
failure and readiness requirements before either application uses them. A
liveness check verifies only that each process responds. Readiness checks will
be added when a real application responsibility requires a dependency.
