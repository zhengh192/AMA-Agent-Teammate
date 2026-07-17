# Analysis Skill Evaluation Guide

## Suite

`evals/generic_cases.yaml` contains exactly 25 synthetic, source-free cases:

- 4 metric-query plans;
- 4 period comparisons;
- 4 trend/anomaly cases;
- 4 contribution cases;
- 3 mix-rate decompositions;
- 2 funnel cases;
- 2 cross-source cases;
- 2 ambiguous questions requiring clarification.

The suite covers incomplete or unusable inputs, join duplication risk, ambiguous aliases, small
samples, non-causal interpretation, mix-only change, rate-only change, and combined effects.
Expected numeric and control-flow behavior is asserted by the evaluator; results are not approved
through snapshots.

## Run

```powershell
uv run python scripts/validate_analysis_skills.py validate
uv run python scripts/evaluate_analysis_skills.py
uv run pytest apps/api/tests/test_analysis_skills.py -q
```

The evaluator exits non-zero when any case fails and prints each case ID and assertion result.
Synthetic cases test deterministic procedures only; they do not claim coverage of production data,
real database dialects, access policy, business definitions, or causal validity.

## Adding cases

Keep the category totals aligned with the acceptance contract or update the strict suite schema and
documentation together. Prefer cases that distinguish a real behavioral decision: clarification,
prerequisite stop, numeric reconciliation, data-confidence downgrade, join-quality warning, or
causal-language rejection.
