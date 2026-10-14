# QuantAI SQL safety and architecture hardening

## Motivation
The deterministic SQL compiler accepted untrusted identifiers, operator text,
sort values, and literals without robust validation. The guard relied partly
on regex keyword matching, and existing LIMIT values were not capped. DataFrames
were retained indefinitely and bulk imports ran on the asyncio event loop.

## What changed
- Validate structured SQL plan input and reject malformed operators/identifiers
- Parse SQL statements with SQLGlot and enforce a bounded outer LIMIT
- Extract bounded TTL cache independent of LangGraph state
- Offload blocking CSV import and SQL execution to worker threads
- Encode MySQL passwords with SQLAlchemy URL.create
- Restrict plot file retrieval to safe local PNG/SVG names
- Add Python regression tests, backend/frontend CI and architecture roadmap

## Verification
- [x] GitHub branch and changes prepared on contributor fork
- [ ] Backend CI unit tests and compileall
- [ ] Frontend TypeScript and Vite build
- [ ] MySQL/Ollama integration tests in a local development environment

## Important scope limits
This is targeted hardening, not full production security. Public hosting still
requires authentication, authorization, quotas, and policy unification across
query, export, and rerun endpoints. Chroma files already tracked in Git remain
untouched. A local cache is not a distributed result store.

See `docs/architecture.md` for the prioritized migration roadmap.
