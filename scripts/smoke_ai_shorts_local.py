#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from huggingface_hub import snapshot_download


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> int:
    root = Path(os.environ.get("LOGICCUT_ROOT", Path(__file__).resolve().parents[1]))
    third_party = root / "third_party" / "AI-Youtube-Shorts-Generator"
    sys.path.insert(0, str(third_party))

    out_dir = Path(os.environ.get("LOCAL_OUTPUT_DIR", root / "output" / "ai-shorts"))
    smoke_dir = out_dir / "smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)

    source = smoke_dir / "source.mp4"
    if not source.exists():
        run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=16000",
            "-t", "4",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k",
            str(source),
        ])

    model_id = os.environ.get("LOCAL_WHISPER_MODEL", "Systran/faster-whisper-base")
    model_path = snapshot_download(model_id, local_files_only=True, cache_dir=os.environ.get("HF_HUB_CACHE"))
    from faster_whisper import WhisperModel
    model = WhisperModel(model_path, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(source), language="en", beam_size=1, vad_filter=False)
    first_segment = next(iter(segments), None)

    from shorts_generator.local.clipper import crop_highlights_local
    highlights = [{
        "title": "LogicCut smoke clip",
        "start_time": 0.2,
        "end_time": 3.5,
        "score": 90,
        "hook_sentence": "smoke",
        "virality_reason": "dependency smoke test",
    }]
    clips = crop_highlights_local(str(source), highlights, aspect_ratio="9:16", out_dir=str(smoke_dir))
    clip_path = Path(clips[0]["clip_url"])
    if not clip_path.exists() or clip_path.stat().st_size == 0:
        raise SystemExit(f"clipper produced no video: {clips}")

    report = {
        "source": str(source),
        "clip": str(clip_path),
        "whisper_model": model_id,
        "whisper_model_path": model_path,
        "transcribed_duration": float(getattr(info, "duration", 0.0)),
        "first_segment_text": getattr(first_segment, "text", None),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
