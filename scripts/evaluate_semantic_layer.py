"""Run the semantic-layer evaluation fixtures offline.

    python scripts/evaluate_semantic_layer.py
    python scripts/evaluate_semantic_layer.py --json

No portal, browser or model is used.  The script exits non-zero when any check
fails, so it can gate a release.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.evaluation import format_report, run_evaluation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args()

    report = run_evaluation()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
