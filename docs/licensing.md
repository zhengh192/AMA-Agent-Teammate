# Licensing and Intellectual Property

## Current status

This repository is private and intended for internal enterprise evaluation. No public/open-source license is granted. The absence of a `LICENSE` file is intentional.

Do not create an MIT `LICENSE` unless the repository owner provides the exact instruction `APPROVE_PUBLIC_MIT` after confirming company intellectual-property ownership and open-source approval. AI-assisted generation does not by itself establish the right to publish code.

## Dependency policy

Every introduced dependency must have its exact locked version, license, source, and usage recorded in `THIRD_PARTY_NOTICES.md` or an automatically generated equivalent reviewed into Git.

The following require explicit legal/security review before adoption:

- GPL, AGPL, LGPL where linkage/distribution obligations are unclear
- SSPL and other source-available licenses
- Copyleft data/model licenses
- Packages with missing, custom, conflicting, or ambiguous license metadata
- Vendored code, copied examples, fonts, images, datasets, and model weights

## Review gates

1. Developer proposes dependency and business need.
2. Lockfile fixes the evaluated version and integrity.
3. Automated license/SBOM report is generated.
4. Reviewer verifies source, transitive dependencies, and distribution context.
5. Legal/security approval is recorded when policy requires it.
6. Notice file and rollback notes are committed with the dependency.

## Planned dependency records

Technologies listed in design documents are candidates, not approved dependencies. Phase 1 must establish an approved baseline for Python, Node, OpenAI SDK, LangGraph, FastAPI, frontend, testing, and observability dependencies based on actual lockfiles.
