from __future__ import annotations

import argparse
from pathlib import Path

from ama_teammate.analysis_skills.registry import AnalysisSkillRegistry


def main() -> int:
    parser = argparse.ArgumentParser(prog="ama-analysis-skills")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="Validate foundation analysis skills.")
    validate.add_argument("--root", type=Path, default=Path("skills"))
    args = parser.parse_args()
    registry, issues = AnalysisSkillRegistry.load(args.root)
    if issues:
        for issue in issues:
            print(f"{issue.code}: {issue.path}: {issue.message}")
        return 1
    active = registry.list_packages()
    print(f"Validated {len(active)} analysis skill package(s) from {args.root}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
