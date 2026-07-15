# ADR-004: Knowledge Retrieval Backend

## Status

Accepted for the Phase 3 local MVP. Revisit before an internal pilot with real enterprise documents.

## Decision

Use authoritative SQLite document/version/chunk records plus a rebuildable hybrid retrieval projection:

- normalized keyword overlap for lexical recall;
- cosine similarity over vectors produced by `EmbeddingProvider`;
- owner, lifecycle status, current version, and index status filters before ranking;
- citations resolved from the selected chunk to document version and page/sheet/section/row/line.

Mock embeddings are deterministic and are the default. Azure embeddings are available only when
`AMA_EMBEDDING_PROVIDER=azure` and an approved Azure embedding deployment is configured.

## Options considered

### pgvector

This fits a future PostgreSQL metadata store and provides an open, portable vector index. It would add
a PostgreSQL service, migration, index tuning, and operational dependency to a local MVP that otherwise
runs on SQLite. It is the preferred first production candidate when metadata moves to PostgreSQL.

### Azure AI Search

This provides managed hybrid search, semantic ranking, filtering, and enterprise scale. It also adds a
separate Azure resource, index schema and ingestion pipeline, identity/network configuration, cost, and
environment-dependent integration tests. It is a strong candidate when managed search and scale justify
the additional operational boundary.

### Local SQLite projection (selected)

This keeps Phase 3 reproducible with the existing local stack, makes access/lifecycle filtering explicit,
and supports deterministic security tests. Vectors are JSON projections, so this is not intended for
large corpora or production latency. The authoritative records remain migration-ready; the projection is
rebuildable, so moving to pgvector or Azure AI Search does not change the governance contract.

## Consequences

- Local setup requires no new service.
- Hybrid ranking is transparent and testable.
- Corpus size, ranking quality, concurrent indexing, and latency are intentionally limited.
- Production selection requires measured corpus/query load, access-filter complexity, regional/network
  policy, disaster recovery, deletion propagation, cost, and retrieval-quality evaluation.
