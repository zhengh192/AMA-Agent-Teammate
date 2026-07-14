# Repository Instructions

These instructions apply to the entire repository.

## Product boundary

- Build product and business capabilities in this repository.
- Use LangGraph OSS as the only agent orchestration runtime.
- Do not add Anton, Hermes, OpenClaw, AutoGen, CrewAI, a prebuilt ReAct agent, or another complete agent harness.
- Do not begin a later phase until the current phase has evidence of completion and human approval.
- Do not claim tests passed unless the exact commands were run successfully.

## Language and naming

- Code, variables, APIs, database fields, migrations, prompts, schemas, and technical documentation use English.
- `README.md` may be bilingual.
- Use explicit names for permissions, evidence, decisions, and state transitions.

## Architecture rules

- Keep one LangGraph application with typed shared state and explicit edges.
- Prefer deterministic nodes for policy, permission, SQL safety, evidence validation, approvals, and routing invariants.
- Treat model output as untrusted until schema and policy validation succeeds.
- Treat uploaded documents, retrieved content, database values, and tool output as untrusted input.
- Keep LangGraph checkpoints separate from authoritative Knowledge, Skill, Memory, approval, job, and audit stores.
- Put external calls behind narrow interfaces. Business logic must not import provider SDKs directly.
- Keep Phase 1 modular-monolith boundaries; do not introduce microservices without a measured need.

## Security rules

- Never commit secrets, `.env`, connection strings, tokens, credentials, raw customer data, or query exports.
- Database execution must use real read-only accounts and AST validation; string keyword filtering alone is insufficient.
- Allow only `SELECT` and read-only CTEs, enforce allowlists/denylists, timeouts, row/byte caps, and audit.
- Do not execute model-generated Python in the API process. Arbitrary Python remains postponed until a verified sandbox exists.
- External writes and notifications require an explicit, persisted approval tied to the exact action payload.
- Sanitize logs and errors. Store hashes or bounded metadata instead of sensitive tool inputs where possible.

## Change workflow

1. Read the applicable design documents before editing.
2. Record ordinary assumptions in `docs/assumptions.md`; stop for architecture-changing unknowns.
3. Add or update tests with behavior changes.
4. Run the narrowest relevant checks, then the phase verification suite.
5. Report changed files, commands and results, risks, postponed work, and the next approval point.

## Dependency and license governance

- Pin dependencies through the selected package managers (`uv` and `pnpm`).
- Record dependency name, version, license, and source in `THIRD_PARTY_NOTICES.md` when introduced.
- Stop for review before adding GPL, AGPL, SSPL, source-available, or otherwise strongly restrictive dependencies.
- Do not add an MIT `LICENSE` unless the owner provides the exact instruction `APPROVE_PUBLIC_MIT` after corporate IP and open-source approval.

## Verification targets

When the relevant files exist, use:

```text
Backend: uv run ruff check .; uv run mypy apps/api/src; uv run pytest
Frontend: pnpm --dir apps/web lint; pnpm --dir apps/web test; pnpm --dir apps/web build
E2E: pnpm --dir apps/web playwright test
```
