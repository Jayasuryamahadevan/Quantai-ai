# QuantAI architecture assessment and migration roadmap

The aim of this first PR is targeted correctness, query safety, and resource
management without breaking React's SSE event contract. It is **not** a
production-ready rewrite.

## Request flow

```text
React UI → FastAPI / SSE → LangGraph planner
                         ├─ source resolver / column selector
                         ├─ structured plan → SQL compiler
                         ├─ SQL AST guard → read-only MySQL
                         ├─ verification / insights / charts
                         └─ bounded per-run cache
Documents → ingestion/OCR → Chroma → local Ollama
Uploads → Pandas → MySQL import user
History/catalog → MySQL app schema
```

## Shipped in this PR

- SQL compilation validates identifiers, operators, literals, sort and LIMIT.
- SQL guard parses complete statements and adds a strict outer-row bound.
- Result storage is in a bounded, thread-safe, expiring core component.
- Blocking bulk import and read-only query execution run in a worker thread.
- MySQL connection strings use SQLAlchemy URL encoding.
- Plot-serving route restricts file extension and resolved upload directory.
- Backend unit tests and frontend build checks run through GitHub Actions.

## Remaining risks and priorities

| Priority | Architectural gap | Next increment |
|---|---|---|
| P0 | Unauthenticated API routes | Keep local-only; add authentication, authorization and source ownership before public hosting |
| P0 | Tracked Chroma binary artifacts | Review contents and remove tracking in a separate privacy-approved PR |
| P1 | app/main.py is roughly 977 lines | Extract versioned routers and QueryService / SourceService with DI |
| P1 | dataset_report.py is roughly 53 KB | Split profile computation, visualization and rendering |
| P1 | Sync DB calls remain in async handlers | Use service/repository interfaces and safe executor bounds |
| P1 | Query SQL still rendered as strings | Introduce SQLAlchemy bind parameters and centralized policy for query, rerun and export |
| P1 | Export rewrites LIMIT with regex | Re-parse SQL AST and reuse authorized query policy |
| P1 | Cache is process-local | Add shared result store for multi-worker deployment |
| P2 | Backend versions only lower-bounded | Add reproducible lockfile and dependency scans |
| P2 | Integration tests need MySQL/Ollama | Add disposable integration environment and smoke fixtures |
| P2 | No request quota/rate limit | Add Pydantic limits, per-session quotas and cancellation controls |

## Proposed target

```text
HTTP/SSE + request DTO + auth policy
              ↓
Application services: Query / Import / Export / History
              ↓
Domain policy: QueryPlan / SourceAccess / Limits / Verification
              ↓
Ports: QueryRepository / LLMGateway / VectorStore / ResultStore
              ↓
Adapters: MySQL / Ollama / Chroma / durable data store
```

Keep deterministic query planning and SQL guards independent of LLM execution.
Avoid introducing microservices until measured scaling requirements justify them.

## Rollout checklist

1. Run Python unit tests and frontend build in CI.
2. Smoke-test local MySQL: upload → query → rerun → export → delete.
3. Verify Ollama and document RAG with representative files.
4. Confirm least-privilege MySQL users and SQL read-only operation.
5. Review concurrency, generated SQL, and memory use under large datasets.
6. Review and merge after checks pass; no automatic changes to upstream main.
