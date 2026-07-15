from __future__ import annotations

import argparse
from pathlib import Path

from ama_teammate.semantic_metadata.registry import SemanticMetadataRegistry


def main() -> int:
    parser = argparse.ArgumentParser(prog="ama-metadata")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="Validate semantic metadata YAML files.")
    validate.add_argument("--root", type=Path, default=Path("knowledge"))
    args = parser.parse_args()
    registry, issues = SemanticMetadataRegistry.load(args.root)
    if issues:
        for issue in issues:
            print(f"ERROR {issue.path} [{issue.code}] {issue.message}")
        return 1
    print(f"Validated {len(registry.list_definitions())} semantic definitions from {args.root}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
