# Governed Skill Registry

Only versions activated through the exact-hash approval service belong here.

```text
<skill-name>/<semantic-version>/
|- SKILL.md
|- metadata.yaml
|- examples/example.md
`- tests/test_cases.yaml
```

`draft` and `pending_approval` proposals remain authoritative database records and are excluded from
runtime discovery. Active versions are immutable. Changes create a new version; deprecation and rollback
preserve historical reproducibility and are audited.
