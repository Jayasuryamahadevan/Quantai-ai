# QuantAI Temporal Multi-Agent Platform (incremental implementation)

## Why Temporal + LangGraph?

Temporal is the durable **job supervisor**, not the reasoning engine:
it persists activity results, handles retries, survives API/worker restarts,
tracks progress and waits for human decisions. LangGraph already implements
dependent domain agents. Running the complete existing LangGraph graph inside
**one Temporal activity** is deliberate: current result DataFrames are
process-local and cannot safely move between workers. Isolating the full graph
also keeps large DataFrames and raw SQL results **out of Temporal history**.

```text
                         FASTAPI API (localhost by default)
          POST /api/analysis/jobs | GET /{job_id} | review | cancel
                                        |
                                  Temporal Server
                                        |
                              AnalystWorkflow (durable)
                                        |
                        prepare_analysis (source metadata)
                                        |
                   execute_agent_team (LangGraph, one activity)
                      |       |       |         |          |
                supervisor  schema   planner    SQL        verify
                            selector           engine      & insight
                                        |
                        review_analysis (policy QA)
                               /             \
                      approved          needs_approval
                         |                    |
                         |            Temporal approval signal
                         |                    |
                        publish_analysis (database idempotency)
                                        |
                                  GET history by run_id
```

## Analyst responsibility matrix

| Analyst responsibility | Existing specialized role | Durable owner | Status |
|---|---|---|---|
| Understand business question, ambiguity | LangGraph supervisor | Temporal analyst job | Implemented |
| Source discovery and schema context | source_resolver, schema_selector | prepare + agent activity | Implemented, local SQL |
| Data ingestion and typing | import_pipeline | existing upload API | Existing; not yet a Temporal workflow |
| Data profiling, missingness, anomaly checks | metadata profile activity, data_summary, dataset_report | dedicated profile + agent activities | Partially implemented |
| Metric/semantic model | query_planner, grounding | agent activity | Partially implemented |
| SQL composition, safety, execution | plan_to_sql, SQL guard, execution node | agent activity | Implemented, follow-up policy gaps |
| Statistical analysis & reconciliation | cross_check, stats_analyzer | agent activity | Implemented, validation coverage pending |
| Visualization | visualizer | agent activity | Implemented |
| Business insight narrative | insight | agent activity | Implemented |
| Independent quality review | deterministic review_analysis | Temporal quality activity | Implemented with human gate |
| Publish reproducible result | QueryRun/Message persistence | publication activity | Implemented |
| Exports and stakeholder reports | export handlers, report-author activity | optional Temporal final activity after approval | PDF automated; other formats via existing API |
| Lineage, data contracts, semantic layer | proposed catalog extensions | future | Not implemented |
| Automated scheduled analysis and drift | Temporal schedule framework | future | Not implemented |
| Collaborative authorization/multitenancy | not available | future | NOT production ready |

## Data contract and idempotency

- Workflow ID is `quantai-analysis-{idempotency_key UUID}`; run_id uses the same UUID.
- Request includes question, source_id, session_id, previous_run_id.
- Only compact metadata flows between Temporal activities.
- Database QueryRun and Message records are the authoritative query-history
  artifacts; writing them is retried idempotently against run_id.
- `prepare_analysis` pins the chosen source_id at workflow start.
- `execute_agent_team` reuses the prior persisted run when retried, and
  calls `activity.heartbeat` after graph node progress.
- The quality gate rejects missing results/errors, asks for clarification
  when ambiguous, and requires human approval for PII, unverified SQL,
  low confidence, grounding problems and free-form fallback.
- A review signal is durable. Approval expires after three days.
- API progress queries do not wait for LLM execution.

## Local startup

Prerequisites: MySQL users/schema and Ollama model from root README; Temporal
CLI installed from https://docs.temporal.io/cli .

Terminal 1:

```bash
temporal server start-dev
```

Terminal 2:

```bash
pip install -r requirements.txt
python -m app.orchestration.worker
```

Terminal 3:

```bash
# .env (keep API on localhost, NEVER expose unauthenticated)
TEMPORAL_ENABLED=true
TEMPORAL_ADDRESS=127.0.0.1:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=quantai-analyst

uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Temporal Web UI: http://localhost:8233

Start (use an existing Source UUID, or omit source_id to select latest):

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/jobs \
  -H 'content-type: application/json' \
  -d '{"question":"What is total sales by region?"}'
```

Use the `job_id` in the returned status URL:

```bash
curl http://127.0.0.1:8000/api/analysis/jobs/quantai-analysis-<uuid>
```

To request a PDF when submitting, set `include_report: true`; the report
is generated only after approval. Enable the frontend workflow panel with
`VITE_ENABLE_TEMPORAL_ANALYSIS=true` in `frontend/.env.local`, and restart
Vite. The default worker handles one activity at a time to avoid cross-loop
use of the existing Ollama semaphore; tune only after concurrency testing.

If `status=waiting_for_approval`, review query outputs/source governance
and then send:

```bash
curl -X POST http://127.0.0.1:8000/api/analysis/jobs/quantai-analysis-<uuid>/review \
  -H 'content-type: application/json' -d '{"approved":true}'
```

Cancel similarly with POST `/cancel`. Once approved, read the answer through
`/api/history/<run_id>`. If a PDF report was requested and produced, download
the exact saved artifact at `GET /api/analysis/jobs/reports/<run_id>`:
this route checks the approved run, checks the recorded file path stays within
the configured export directory, and **does not re-execute SQL**. If a saved
file disappears, the report activity fails without silently rebuilding it
from mutable data, while the approved analytical answer remains available.

**Snapshot limitation:** the existing export renderer executes the saved SQL
when generating a *new* PDF. If underlying data changes between the analysis
and initial report generation, values can differ. Before enterprise rollout,
persist a versioned query-result snapshot, then derive all charts/reports from
that immutable snapshot. Other ad-hoc export endpoints still re-execute SQL.

## Security/operational limitations before production

1. **Do not expose FastAPI publicly.** No user login, tenant isolation, source
   authorization, quota or audit identity. Reviewer signal authorization is
   not user-specific. Deploy loopback-only until these are implemented.
2. An API job starts without waiting for a worker. Unavailable workers leave
   jobs queued and visible in Temporal; operations need alerts.
3. Heavy LangGraph nodes share one activity due to in-memory DataFrames.
   Split into per-role activities only after introducing a durable artifact
   store (object storage, DB or distributed result cache).
4. Activity completion is persisted but a process crash can still repeat
   model inference if the DB write did not commit. Idempotency prevents
   duplicate published chat messages after a successful DB write.
5. Export/rerun routes need the same SQL and source authorization policy;
   graph result caches are not distributed. No hard cost or memory quotas yet.
6. Existing code logs and uses external dependencies: test privacy, PII and
   permissions before deploying beyond a trusted machine.
7. Clean up `review_pending` rows after cancellations and failures; enforce
   database migrations, retention and artifact lifecycle policies.
8. Use Temporal Cloud or persistent Temporal Server for real durability;
   `temporal server start-dev` is **development only**, not HA.

## Validation

- CI: Python compileall, unit QA/workflow tests and React production build.
- Test offline unit policy without Temporal server.
- **Required before merge:** real Temporal Worker + API + MySQL + Ollama end-to-end
  (upload, valid query, unverified gate/review, cancel, service restart, duplicate
  request idempotency, history/export).
- For load testing: measure active Temporal worker concurrency, MySQL pool,
  Ollama GPU contention, workflow-history growth and response latency.

## Proposed next PRs

1. Per-user auth/tenant isolation and audit actors on every job.
2. QueryResultStore adapter for durable parquet/JSON artifacts with retention.
3. Turn profiling, cleaning, semantic metrics and reporting into independently
   retryable child workflows with versioned payload contracts.
4. Temporal Schedules for refresh/drift/report dispatch and alert policies.
5. SQL semantic model, validated metric definitions and a reproducible
   benchmark suite for numeric correctness.
