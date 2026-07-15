# Governed Asset Accumulation Model

## Purpose

The pilot should become more useful through explicit, reviewable accumulation rather than silent model
learning. Conversation may produce a draft, but only an approved asset can influence later Agent runs.
Every active asset has provenance, a version, a lifecycle state, and an audit trail.

## Asset boundaries

| Asset | Use it for | Canonical representation | Do not use it for |
|---|---|---|---|
| Knowledge | Business definitions, policies, data dictionaries, processes, reference material | Versioned source document plus metadata, parsed chunks, and citations | Behavioral instructions or uncited inferred facts |
| Skill | A repeatable method the Agent should follow for a matching task | Git-tracked package with `SKILL.md`, `metadata.yaml`, examples, and tests | Business facts, secrets, or unbounded tool authority |
| Memory | Small explicit preferences or durable context tied to a user, project, or entity | Structured scope/key/value record with source, version, expiry, and status | Raw chat history, source documents, query exports, or hidden inference |

## Knowledge format

Knowledge keeps the original source format when practical: PDF, DOCX, XLSX, CSV, TXT, or Markdown. The
authoritative record also stores source owner, classification, effective date, version, content hash,
parser status, and precise page/sheet/section/row/line locations. Retrieved content remains untrusted data
and never becomes an instruction merely because a source was approved.

Conflicting active definitions are separate records linked by an open conflict. They are not silently
merged. A production rollout must add enterprise access control, malware quarantine, retention, and legal
hold policy.

## Skill package format

Each approved version is a directory under the Git-tracked Skill registry:

```text
skills/registry/<skill-name>/<semantic-version>/
|-- SKILL.md
|-- metadata.yaml
|-- examples/
|   `-- example.md
`-- tests/
    `-- test_cases.yaml
```

- `SKILL.md` contains concise operating instructions, applicability, required evidence, and safety rules.
- `metadata.yaml` declares name, semantic version, owner, purpose, input/output contracts, permissions,
  tool allowlist, lifecycle status, approval binding, and rollback version.
- `examples/` demonstrates intended use without granting authority.
- `tests/` records positive and negative behavioral cases, including prohibited operations.

The proposal diff and its SHA-256 hash are reviewed before activation. Active versions may be deprecated;
rollback is explicit and audited. An unapproved draft is never loaded into runtime discovery.

## Memory format

Memory is a bounded structured record, not a Markdown knowledge base:

```json
{
  "scope": "user_preference | project | entity",
  "key": "stable_machine_readable_name",
  "value": { "text": "explicit approved context" },
  "source": "who or what explicitly supplied it",
  "version": 1,
  "expires_at": null,
  "status": "pending_approval | active | rejected | expired | deleted"
}
```

Edits create a new proposal. Secrets are rejected, expiry is enforced, deletion clears the value, and no
conversation inference silently creates or updates long-term Memory.

## Controlled accumulation loop

1. A user teaches or states something in the Agent, or an administrator uploads/drafts it.
2. The system creates a bounded `pending_approval` asset with provenance and an exact hash.
3. An administrator reviews the source, diff, examples, tests, permissions, conflicts, and expiry.
4. Exact approval activates the asset; rejection leaves it inert.
5. Matching Agent runs may use active assets and record `knowledge.invoked`, `skill.invoked`, or
   `memory.invoked` audit events.
6. Owners periodically correct, supersede, deprecate, expire, or delete assets.

## Administration routes

- `/admin` — accumulation overview and lifecycle
- `/admin/knowledge` — sources, citations, retrieval checks, and conflicts
- `/admin/skills` — file-based packages, exact diffs, approval, deprecation, and rollback
- `/admin/memory` — structured proposals, active records, expiry, and deletion
