#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logiccut.external_adapter_benchmark import run_external_adapter_pocs  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run external highlight adapter POCs on LogicCut materials.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "output" / "external-adapter-poc",
        help="Directory for adapter outputs and showcase HTML.",
    )
    parser.add_argument("--limit", type=int, default=4, help="Highlights per source to render.")
    parser.add_argument("--no-render", action="store_true", help="Only rebuild reports from existing outputs.")
    parser.add_argument("--no-blackdetect", action="store_true", help="Skip ffmpeg blackdetect checks.")
    args = parser.parse_args(argv)

    result = run_external_adapter_pocs(
        repo_root=ROOT,
        output_dir=args.output_dir,
        limit=args.limit,
        render=not args.no_render,
        run_blackdetect=not args.no_blackdetect,
    )
    print(result["index"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
