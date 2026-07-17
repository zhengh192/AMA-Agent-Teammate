from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))


if __name__ == "__main__":
    cli = import_module("ama_teammate.analysis_skills.cli")
    raise SystemExit(cli.main())
