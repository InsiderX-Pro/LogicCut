from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .media import concat_videos_reencode, ffprobe_duration


def merge_videos(inputs: list[Path], output: Path, *, manifest_path: Path | None = None) -> dict[str, Any]:
    if len(inputs) < 1:
        raise ValueError("merge requires at least one input video")
    for item in inputs:
        if not item.exists():
            raise FileNotFoundError(item)

    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = manifest_path or output.with_name(output.stem + "_merge_manifest.json")
    input_items = [{"path": str(item), "duration": ffprobe_duration(item)} for item in inputs]
    concat_videos_reencode(inputs, output)
    output_duration = ffprobe_duration(output)
    result = {
        "version": "0.3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_video": str(output),
        "duration": output_duration,
        "inputs": input_items,
        "manifest": str(manifest),
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
