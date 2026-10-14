# QuantAI: durable specialist-agent execution (PR #3)

This change upgrades the first Temporal foundation from one opaque LangGraph
activity to **recoverable analyst roles with database checkpoints**. It keeps
the existing FastAPI and LangGraph interfaces available and avoids a risky
large-scale rewrite.

## Analyst roles and delivery boundaries

| Responsibility | Existing domain specialist | Temporal stage | Durable independently? |
|---|---|---|---|
| Business request/intent | supervisor | `supervise_analysis` | Yes, checkpoint |
| Data catalog/lineage discovery | source_resolver | `discover_schema` | Yes, checkpoint |
| Data profiling / quality | ColumnCatalog statistics | `profile_source` | Yes, activity result |
| KPI interpretation and column selection | column_selector, query_planner | `plan_analysis` | Yes, checkpoint |
| SQL author / optimizer | sql_compile | `execute_analysis` | Within analysis activity |
| SQL safety and read-only execution | validate_execute | `execute_analysis` | Within analysis activity |
| Numerical verification and repair | cross_check, bounded retry | `execute_analysis` | Within analysis activity |
| Cleaning, statistics | cleaner, stats_analyzer | `execute_analysis` | Within analysis activity |
| Data visualization and insights | visualizer, insight, confidence | `execute_analysis` | Within analysis activity |
| Independent QA / approval | deterministic quality policy | `review_analysis`, signal | Yes |
| Report publishing | publish_analysis, deliver_report | Activities | Yes |

Agents are **not independent services**. The query executor, Pandas statistics,
visualization and insight stages intentionally share one worker activity because
their current DataFrames are process-local. Decoupling them requires a real
snapshot/artifact store and versioned transfer contracts.

## Durable flow

```text
HTTP POST analysis/jobs
      |
Temporal AnalystWorkflow
      |
prepare_analysis (pin source/session, validate context)
      |
profile_source (catalog coverage, missingness, PII)
      |
supervise_analysis ────────▶ MySQL analyst_checkpoints
      |
discover_schema ───────────▶ MySQL analyst_checkpoints
      |
plan_analysis ─────────────▶ MySQL analyst_checkpoints
      |                           |
      |                 Retry reads committed stage;
      |                 does not repeat finished LLM steps
      |
execute_analysis (SQL compile → AST guard → constrained query
      |           → cross-check / repair → stats / visuals / narrative)
      |
QueryRun / concise quality trace
      |
review_analysis ── needs approval? ──▶ Temporal approval signal
      |
publish_analysis → Chat history + delete transient checkpoints
      |
(optional) deliver_report → approved PDF artifact
```

Temporal event history carries only small stage decisions and QA summaries,
not raw SQL result DataFrames or full schema catalogs.

## Error policy

- Every role checkpoints only after a successful state transition.
- MySQL checkpoints are at-most-2-MB serialized JSON metadata. Unsupported
  values, NaNs and DataFrames fail instead of silently entering workflow history.
- Stages fail closed when their prerequisite checkpoint does not exist.
- Clarification requests do not invoke unnecessary planner / SQL roles.
- SQL repair has a hard retry budget (two repairs). Exceeding it produces an
  explicit error record, not an invented success.
- Long-running local model calls heartbeat every 20 seconds.
- Numerical-claim checking feeds the independent final reviewer.
- Final publication deletes transient checkpoint records. Interrupted/failed
  jobs still need a scheduled retention sweeper.

## Setup and migrations

Start from the stacked branch order: PR #1 → PR #2 → PR #3.

MySQL application schema must contain `analyst_checkpoints`. The existing
application startup imports models and calls `Base.metadata.create_all`.
This creates the new table on a fresh local database with appropriate app
permissions. For production, use explicit Alembic migrations instead of
relying on `create_all`. Start the FastAPI backend at least once before
starting the Temporal worker. Keep all endpoints local-only.

See `docs/temporal-multi-agent.md` for Temporal CLI, Ollama, MySQL and frontend
feature-flag setup.

## Validation evidence

- Python static compile and backend unit tests
- SQLite-backed checkpoint persistence / idempotency / payload tests
- Mocked specialist resume and clarification handling
- Temporal test-server workflow execution using registered stage activities
- TypeScript/Vite production build

None of these substitutes for production MySQL, real Ollama model, file
exports, restarts, and data correctness end-to-end.

## Remaining release blockers

1. User authentication, per-source authorization and audit actor identities.
2. Immutable Parquet/Arrow query-result snapshots with checksums and retention.
3. Temporal worker crash/restart and cancellation integration tests against
   real MySQL/Ollama, including network loss and forced process termination.
4. Bounded worker/GPU concurrency, quotas, tracing/metrics and alerting.
5. Schema migrations, checkpoint expiry sweeper and secure data retention.
6. True semantic KPI registry with testable metric definitions and provenance.
7. No deterministic update of already-running Temporal workflow history:
   use workflow versioning / Build IDs when upgrading an existing deployment.

Keep this branch in draft until the above boundaries are explicitly evaluated.
