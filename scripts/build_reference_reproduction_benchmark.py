#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logiccut.reference_benchmark import default_reference_cases, write_benchmark_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build LogicCut reference reproduction benchmark pages.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "output/reference-reproduction-benchmark",
        help="Directory for index.html, case pages, JSON reports and copied baseline videos.",
    )
    parser.add_argument("--no-blackdetect", action="store_true", help="Skip ffmpeg blackdetect checks.")
    args = parser.parse_args(argv)

    result = write_benchmark_package(
        repo_root=ROOT,
        output_dir=args.output_dir,
        cases=default_reference_cases(ROOT),
        run_blackdetect=not args.no_blackdetect,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
