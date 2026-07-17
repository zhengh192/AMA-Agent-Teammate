# Governed Skills

Immediate `skills/<skill_id>/` directories are reviewed Foundation Analysis Skills. Each package
contains strict `metadata.yaml`, concise `SKILL.md`, and asserted tests. Application startup
validates active packages and their prerequisite graph.

`skills/registry/` is a separate Phase 3 store for user-proposed Skill versions activated through
the existing exact-hash approval workflow. Proposal packages cannot override a Foundation Analysis
Skill.

Only approved active versions participate in execution planning. Draft, invalid, future,
deprecated, rejected, and pending-approval content is excluded. Deterministic calculations live in
the shared controlled analysis library rather than executable model-generated scripts inside
