from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from ama_teammate.analysis_skills.evaluator import (  # noqa: E402
    load_evaluation_suite,
    run_evaluation_suite,
)
from ama_teammate.analysis_skills.registry import AnalysisSkillRegistry  # noqa: E402

registry, issues = AnalysisSkillRegistry.load(ROOT / "skills")
if issues:
    for issue in issues:
        print(f"FAIL registry {issue.code}: {issue.message}")
    raise SystemExit(1)

suite = load_evaluation_suite(ROOT / "evals/generic_cases.yaml")
results = run_evaluation_suite(suite, registry)
for result in results:
    print(f"{'PASS' if result.passed else 'FAIL'} {result.case_id}: {result.detail}")
passed = sum(result.passed for result in results)
print(f"Evaluation result: {passed}/{len(results)} passed.")
raise SystemExit(0 if passed == len(results) else 1)
