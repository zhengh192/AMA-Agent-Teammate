# Phase 3 Implementation

## Delivered flow

`Upload -> type/signature/security validation -> mock scan -> safe parser -> versioned chunks -> mock/Azure embedding -> hybrid retrieval -> exact citation`

Knowledge, Skill, Memory, and approvals are authoritative SQLite domain records. LangGraph checkpoints
contain no full uploads, active Skill content, long-term Memory values, or approval authority.

## Document ingestion

Supported formats are PDF, DOCX, XLSX, CSV, TXT, and Markdown. The API validates extension, media type,
signature, byte size, ZIP entry count/expansion ratio, Office package structure, macros, embedded objects,
external links, page/sheet/row/line limits, and UTF-8 text. Originals are content-addressed under the
configured artifact root. Chunks preserve page, sheet, section, row, or line locations and parser version.

Uploaded text is always stored with `untrusted_source` trust. It is never interpreted as system policy,
never invokes tools, and never creates a Skill or Memory proposal by itself.

## Retrieval and conflicts

The MVP uses the backend selected in `docs/adr-004-knowledge-retrieval.md`: owner-filtered current SQLite
chunks with lexical and vector ranking. Mock embeddings are deterministic. Azure embeddings are isolated
inside the provider layer and use environment configuration only. A result without an authorized source
is `Unknown`. Different active definitions for the same structured Knowledge kind/name create an open
conflict and the answer becomes `Need confirmation`; no definition is silently preferred.

Structured Knowledge kinds are business context, metric definition, data source, table, field, business
rule, and process. Records retain source version, chunk, effective date, owner metadata, and deprecation
state.

## Skill lifecycle

Natural-language teaching creates only a `pending_approval` proposal with a canonical diff and SHA-256
payload hash. The required conversion-decline teaching example creates `SKILL.md`, `metadata.yaml`, a
positive example, and positive/negative test cases in the diff. No draft file enters runtime discovery.

Approval must present the exact hash. Activation writes a versioned folder under `skills/registry`, marks
the prior active version superseded, and records a rollback pointer. Only active versions are added to
matching chat/analysis context; invocation is audited by name/version. Rejection, deprecation, and rollback
are explicit endpoints and audit events.

## Memory lifecycle

Session state remains chat/checkpoint state. Long-term project, user preference, and entity Memory uses a
proposal with source, exact hash, approval, version, expiry, correction (a new proposal), and explicit
deletion. Secret-like keys/values are rejected. No conversation inference silently updates Memory.

## Agent and administration boundary

The front-office Agent runs at `/` and exposes conversation and governed analysis only. Knowledge, Skill,
and Memory maintenance is separated into /admin/knowledge, /admin/skills, and /admin/memory,
with /admin as the governed accumulation overview. Explicit natural-language forms in the Agent can create
`pending_approval` proposals: `knowledge proposal: ...`, `memory: ...`, and teaching phrased as
`when analyzing ...`. Proposal creation completes the chat run and directs the user to administration.
No pending or rejected record enters retrieval, Skill context, or Memory context. Exact-hash approval in
administration activates the record, and later invocation is audited. Uploaded/retrieved text remains
untrusted data even after source approval and can never supply system instructions.

## Demo workflow

1. Open the Agent at `/`, create a session, and send
   `knowledge proposal: Metric: Net Revenue = invoiced revenue less refunds`.
2. Confirm that the Agent reports `Need confirmation` and completes the chat run. Open `/admin`; the
   document is `pending_approval`, has a content preview and exact hash, and does not answer retrieval yet.
3. Approve the exact document in administration, run the retrieval check, and inspect the versioned
   citation. Upload a conflicting active definition and inspect the `Need confirmation` conflict.
4. In the Agent, teach `When analyzing conversion decline, first check completeness, then Geo, Channel,
   and Intent contribution, and separate confirmed causes from inference.`
5. In /admin/skills, inspect the SKILL.md, metadata.yaml, examples, tests, and exact package diff,
   then approve it. Run a matching analysis and inspect
   `skill.invoked` in the trace.
6. Send `memory: Use CNY as the default currency for finance reports.` in the Agent. Approve, reject,
   edit, expire, or delete it only in `/admin/memory`; inspect `memory.invoked` after approval.
## API summary

- `POST /api/documents/upload`, `GET /api/documents`, exact document decision
- `POST /api/knowledge/ask`, `GET /api/knowledge/conflicts`
- `POST/GET /api/skills/proposals`, exact decision, deprecate, rollback
- `POST/GET /api/memories/proposals`, exact decision, list, edit proposal, delete
- `GET /api/providers/embeddings/smoke`

The canonical asset formats and accumulation decision guide are documented in `docs/governed-assets.md`.

## Security limitations

- `mock_clean` is a development scanner contract, not production malware scanning or quarantine.
- Local artifacts and SQLite files rely on workstation access controls and are not an approved encrypted
  production store.
- The in-process local index is intentionally bounded and not suitable for a large or multi-tenant corpus.
- Access control is the documented single development identity; enterprise SSO/RBAC remains required.
- Office parsing disables active content but does not replace a production content-disarm/reconstruction
  pipeline.
- Azure embedding smoke testing requires a real embedding deployment; an LLM deployment is not assumed to
  support embeddings.
- No arbitrary Python, external write, Jira job, notification, or Phase 4 capability was added.

## Rollback

Set `AMA_EMBEDDING_PROVIDER=mock`, deprecate active Skill versions, delete approved Memory through the API,
stop the app, and restore/revert the Phase 3 metadata and source checkpoint. Document originals and indexes
must follow the approved retention/deletion policy; deleting a LangGraph checkpoint does not delete or
activate governed records.
