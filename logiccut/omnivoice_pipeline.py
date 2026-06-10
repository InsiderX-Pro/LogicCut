from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import shutil
import socket
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

from .html_cards import build_highlight_card, render_html_card_video, render_intro_html_card_video
from .media import burn_subtitles, concat_videos_reencode, ffprobe_duration, render_clip


@dataclass(frozen=True)
class SpeechSegment:
    start: float
    end: float
    text: str


def merge_segments_for_dubbing(
    segments: list[dict[str, Any]],
    *,
    max_duration: float = 18.0,
    max_chars: int = 220,
) -> list[SpeechSegment]:
    merged: list[SpeechSegment] = []
    current: list[dict[str, Any]] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        if end <= start:
            continue
        current_start = float(current[0]["start"]) if current else start
        next_text = " ".join([*(str(item["text"]).strip() for item in current), text])
        would_exceed_duration = current and end - current_start > max_duration
        would_exceed_chars = current and len(next_text) > max_chars
        if would_exceed_duration or would_exceed_chars:
            merged.append(_collapse_segments(current))
            current = []
        current.append({"start": start, "end": end, "text": text})
    if current:
        merged.append(_collapse_segments(current))
    return merged


def _collapse_segments(segments: list[dict[str, Any]]) -> SpeechSegment:
    return SpeechSegment(
        start=float(segments[0]["start"]),
        end=float(segments[-1]["end"]),
        text=" ".join(str(item["text"]).strip() for item in segments if str(item.get("text", "")).strip()),
    )


def write_srt(path: Path, segments: list[SpeechSegment]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(f"{_srt_time(segment.start)} --> {_srt_time(segment.end)}")
        lines.append(segment.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_vtt(path: Path, segments: list[SpeechSegment]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["WEBVTT", ""]
    for segment in segments:
        lines.append(f"{_vtt_time(segment.start)} --> {_vtt_time(segment.end)}")
        lines.append(segment.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def _vtt_time(seconds: float) -> str:
    return _srt_time(seconds).replace(",", ".")


def post_multipart(api: str, path: str, *, fields: dict[str, str] | None = None, files: dict[str, Path] | None = None) -> Any:
    boundary = f"----logiccut{int(time.time() * 1000)}"
    body: list[bytes] = []
    for name, value in (fields or {}).items():
        body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    for name, file_path in (files or {}).items():
        media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        body.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{file_path.name}\"\r\n"
            f"Content-Type: {media_type}\r\n\r\n".encode()
        )
        body.append(file_path.read_bytes())
        body.append(b"\r\n")
    body.append(f"--{boundary}--\r\n".encode())
    return _request(api, path, body=b"".join(body), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


def post_json(api: str, path: str, payload: dict[str, Any]) -> Any:
    return _request(
        api,
        path,
        body=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def get_json(api: str, path: str, query: dict[str, str] | None = None) -> Any:
    if query:
        path = path + "?" + urllib.parse.urlencode(query)
    return _request(api, path, method="GET")


def _request(
    api: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    method: str = "POST",
    timeout: float = 3600.0,
) -> Any:
    url = urllib.parse.urlparse(api.rstrip("/") + path)
    conn = HTTPConnection(url.hostname, url.port or 80, timeout=timeout)
    conn.request(method, url.path + (f"?{url.query}" if url.query else ""), body=body, headers=headers or {})
    response = conn.getresponse()
    data = response.read()
    if response.status >= 400:
        raise RuntimeError(f"{method} {path} -> {response.status}: {data.decode(errors='replace')[:1200]}")
    content_type = response.getheader("Content-Type", "")
    if content_type.startswith("application/json"):
        return json.loads(data.decode("utf-8"))
    return data


def stream_task(
    api: str,
    task_id: str,
    log_path: Path,
    *,
    read_timeout: float = 45.0,
    completion_probe: Any | None = None,
) -> list[dict[str, Any]]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    events: list[dict[str, Any]] = []
    url = api.rstrip("/") + f"/tasks/stream/{task_id}"
    with log_path.open("a", encoding="utf-8") as log:
        while True:
            try:
                with urllib.request.urlopen(url, timeout=read_timeout) as response:
                    buffer = b""
                    while True:
                        chunk = response.read(4096)
                        if not chunk:
                            status = _task_status(api, task_id)
                            if status == "done" or (completion_probe and completion_probe()):
                                _log_synthetic_done(log, task_id, status or "complete")
                                return events
                            if status in {"failed", "cancelled"}:
                                raise RuntimeError(f"OmniVoice task {task_id} ended as {status}")
                            break
                        buffer += chunk
                        while b"\n\n" in buffer:
                            frame, buffer = buffer.split(b"\n\n", 1)
                            event = _parse_sse_frame(frame.decode("utf-8", errors="replace"))
                            if not event:
                                continue
                            events.append(event)
                            log.write(json.dumps(event, ensure_ascii=False) + "\n")
                            log.flush()
                            payload = event.get("data") or {}
                            event_type = payload.get("type") or event.get("event")
                            if event_type in {"error", "cancelled"}:
                                raise RuntimeError(f"OmniVoice task {task_id} failed: {payload}")
                            if event_type in {"ready", "done"}:
                                return events
            except (TimeoutError, socket.timeout):
                status = _task_status(api, task_id)
                if status == "done" or (completion_probe and completion_probe()):
                    _log_synthetic_done(log, task_id, status or "complete")
                    return events
                if status in {"failed", "cancelled"}:
                    raise RuntimeError(f"OmniVoice task {task_id} ended as {status}")
                continue
    return events


def _log_synthetic_done(log: Any, task_id: str, reason: str) -> None:
    event = {"event": "logiccut", "data": {"type": "done", "task_id": task_id, "reason": reason}}
    log.write(json.dumps(event, ensure_ascii=False) + "\n")
    log.flush()


def _task_status(api: str, task_id: str) -> str | None:
    try:
        jobs = _request(api, "/jobs?limit=500", method="GET", timeout=15.0)
    except Exception:
        return None
    if not isinstance(jobs, list):
        return None
    for job in jobs:
        if job.get("id") == task_id:
            return str(job.get("status") or "")
    return None


def _dub_track_info(api: str, job_id: str, language_code: str) -> dict[str, Any] | None:
    try:
        payload = _request(api, f"/dub/tracks/{job_id}", method="GET", timeout=15.0)
    except Exception:
        return None
    tracks = payload.get("tracks", {}) if isinstance(payload, dict) else {}
    track = tracks.get(language_code)
    if not isinstance(track, dict):
        return None
    path = track.get("path")
    if path and Path(path).exists() and Path(path).stat().st_size > 0:
        return track
    return None


def _dub_job_snapshot(api: str, job_id: str) -> dict[str, Any] | None:
    try:
        jobs = _request(api, "/jobs?limit=500", method="GET", timeout=15.0)
    except Exception:
        return None
    if not isinstance(jobs, list):
        return None
    for job in jobs:
        if job.get("id") == job_id:
            return job
    return None


def _auto_clone_profiles(job: dict[str, Any] | None) -> dict[str, str]:
    if not job:
        return {}
    clones = job.get("speaker_clones") or {}
    if not isinstance(clones, dict):
        return {}
    return {
        str(speaker_id): f"auto:{_safe_speaker_name(str(speaker_id))}"
        for speaker_id, info in clones.items()
        if isinstance(info, dict) and info.get("ref_audio")
    }


def _safe_speaker_name(speaker_id: str) -> str:
    cleaned: list[str] = []
    for char in speaker_id.lower():
        if char.isalnum():
            cleaned.append(char)
        elif char in (" ", "-"):
            cleaned.append("_")
    return "".join(cleaned) or "speaker"


def _profile_for_segment(
    segment: dict[str, Any],
    *,
    source_segments: list[dict[str, Any]],
    clone_profiles: dict[str, str],
    fallback_profile_id: str = "",
) -> str:
    if not clone_profiles:
        return fallback_profile_id
    speaker_id = str(segment.get("speaker_id") or "").strip()
    if not speaker_id:
        speaker_id = _dominant_speaker_for_time_slot(segment, source_segments)
    if speaker_id in clone_profiles:
        return clone_profiles[speaker_id]
    if len(clone_profiles) == 1:
        return next(iter(clone_profiles.values()))
    return fallback_profile_id


def _dominant_speaker_for_time_slot(segment: dict[str, Any], source_segments: list[dict[str, Any]]) -> str:
    start = float(segment.get("start", 0.0) or 0.0)
    end = float(segment.get("end", start) or start)
    best_speaker = ""
    best_overlap = 0.0
    for source in source_segments:
        speaker_id = str(source.get("speaker_id") or "").strip()
        if not speaker_id:
            continue
        source_start = float(source.get("start", 0.0) or 0.0)
        source_end = float(source.get("end", source_start) or source_start)
        overlap = max(0.0, min(end, source_end) - max(start, source_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = speaker_id
    return best_speaker


def _create_source_voice_profile(
    *,
    api: str,
    job_id: str,
    project_dir: Path,
    language: str,
    log_path: Path,
) -> dict[str, Any] | None:
    job_dir = _local_omnivoice_job_dir(job_id)
    vocals_path = job_dir / "vocals.wav"
    transcript_path = project_dir / "assets" / "source_transcript.json"
    if not vocals_path.exists() or not transcript_path.exists():
        return None
    source_segments = json.loads(transcript_path.read_text(encoding="utf-8")).get("segments") or []
    reference_path = job_dir / "logiccut_source_voice_ref.wav"
    reference = _extract_reference_wav(vocals_path, source_segments, reference_path)
    if reference is None:
        return None
    result = post_multipart(
        api,
        "/profiles",
        fields={
            "name": f"LogicCut source voice {job_id}",
            "ref_text": reference["ref_text"],
            "instruct": "",
            "language": language,
        },
        files={"ref_audio": reference_path},
    )
    profile_id = str(result.get("id") or "").strip()
    payload = {
        "profile_id": profile_id,
        "ref_audio": str(reference_path),
        "ref_text": reference["ref_text"],
        "duration": reference["duration"],
        "source_count": reference["source_count"],
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(json.dumps({"event": "source_voice_profile", "data": payload}, ensure_ascii=False) + "\n")
    return payload if profile_id else None


def _local_omnivoice_job_dir(job_id: str) -> Path:
    data_dir = os.environ.get("OMNIVOICE_DATA_DIR")
    if data_dir:
        return Path(data_dir) / "dub_jobs" / job_id
    return Path("output") / "omnivoice-data" / "dub_jobs" / job_id


def _extract_reference_wav(
    vocals_path: Path,
    source_segments: list[dict[str, Any]],
    output_path: Path,
    *,
    min_duration: float = 5.0,
    ideal_duration: float = 8.0,
    max_duration: float = 15.0,
) -> dict[str, Any] | None:
    try:
        import numpy as np
        import soundfile as sf
    except Exception:
        return None
    usable = [
        segment
        for segment in source_segments
        if str(segment.get("text") or "").strip()
        and float(segment.get("end", 0.0) or 0.0) > float(segment.get("start", 0.0) or 0.0)
    ]
    ranked = sorted(
        usable,
        key=lambda segment: float(segment.get("end", 0.0) or 0.0) - float(segment.get("start", 0.0) or 0.0),
        reverse=True,
    )
    picked: list[dict[str, Any]] = []
    total = 0.0
    for segment in ranked:
        duration = float(segment.get("end", 0.0) or 0.0) - float(segment.get("start", 0.0) or 0.0)
        if duration <= 0:
            continue
        if total + duration > max_duration and picked:
            break
        picked.append(segment)
        total += duration
        if total >= ideal_duration:
            break
    if total < min_duration:
        return None
    picked.sort(key=lambda segment: float(segment.get("start", 0.0) or 0.0))
    audio, sample_rate = sf.read(vocals_path, dtype="float32", always_2d=False)
    if getattr(audio, "ndim", 1) > 1:
        audio = audio.mean(axis=1)
    parts = []
    for segment in picked:
        start = max(0, int(float(segment.get("start", 0.0) or 0.0) * sample_rate))
        end = min(len(audio), int(float(segment.get("end", 0.0) or 0.0) * sample_rate))
        if end > start:
            parts.append(audio[start:end])
    if not parts:
        return None
    gap = np.zeros(int(0.02 * sample_rate), dtype="float32")
    stitched = []
    for index, part in enumerate(parts):
        if index:
            stitched.append(gap)
        stitched.append(part.astype("float32", copy=False))
    output = np.concatenate(stitched)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, output, sample_rate)
    return {
        "ref_text": " ".join(str(segment.get("text") or "").strip() for segment in picked).strip(),
        "duration": float(len(output)) / float(sample_rate),
        "source_count": len(picked),
    }


def _parse_sse_frame(frame: str) -> dict[str, Any] | None:
    event_name = ""
    data_lines: list[str] = []
    for line in frame.splitlines():
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
    if not data_lines:
        return None
    raw = "\n".join(data_lines)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw": raw}
    return {"event": event_name, "data": data}


def run_dub_pipeline(
    *,
    api: str,
    source_video: Path,
    project_dir: Path,
    output_dir: Path,
    job_id: str,
    max_duration: float,
    max_chars: int,
    language: str,
    language_code: str,
    instruct: str,
    num_step: int,
    timing_strategy: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    logs_dir = output_dir / "logs"
    dubbed_video = output_dir / "videos" / "chinese_translation_omnivoice_dub.mp4"
    dubbed_video.parent.mkdir(parents=True, exist_ok=True)
    translated_path = project_dir / "assets" / "translated_segments.json"
    translated = json.loads(translated_path.read_text(encoding="utf-8"))["segments"]
    merged = merge_segments_for_dubbing(translated, max_duration=max_duration, max_chars=max_chars)
    merged_srt = write_srt(assets_dir / "omnivoice_merged_zh.srt", merged)
    merged_vtt = write_vtt(assets_dir / "omnivoice_merged_zh.vtt", merged)
    manifest_path = assets_dir / "omnivoice_dub_manifest.json"

    if dubbed_video.exists() and dubbed_video.stat().st_size > 0:
        previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        manifest = {
            "job_id": job_id,
            "source_video": str(source_video),
            "project_dir": str(project_dir),
            "merged_srt": str(merged_srt),
            "merged_vtt": str(merged_vtt),
            "merged_segment_count": len(merged),
            "imported_segment_count": previous.get("imported_segment_count"),
            "reused_existing_track": True,
            "speaker_clone_profiles": previous.get("speaker_clone_profiles"),
            "source_voice_profile": previous.get("source_voice_profile"),
            "language": language,
            "language_code": language_code,
            "instruct": instruct,
            "num_step": num_step,
            "timing_strategy": timing_strategy,
            "omnivoice_track": previous.get("omnivoice_track"),
            "dubbed_video": str(dubbed_video),
            "export": {"status": "reused_existing_video", "path": str(dubbed_video)},
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return manifest

    track_info = _dub_track_info(api, job_id, language_code)
    segments: list[dict[str, Any]] = []
    clone_profiles: dict[str, str] = {}
    source_voice_profile: dict[str, Any] | None = None
    if track_info is None:
        upload = post_multipart(
            api,
            "/dub/upload",
            fields={"job_id": job_id, "input_type": "video"},
            files={"video": source_video},
        )
        stream_task(api, upload["task_id"], logs_dir / "prep.jsonl")
        source_job = _dub_job_snapshot(api, job_id) or {}
        source_segments = list(source_job.get("segments") or [])
        clone_profiles = _auto_clone_profiles(source_job)
        if not clone_profiles:
            source_voice_profile = _create_source_voice_profile(
                api=api,
                job_id=job_id,
                project_dir=project_dir,
                language=language,
                log_path=logs_dir / "source_voice_profile.jsonl",
            )
        fallback_profile_id = str((source_voice_profile or {}).get("profile_id") or "")
        imported = post_multipart(api, f"/dub/import-srt/{job_id}", files={"file": merged_srt})
        segments = imported["segments"]
        segment_ids = [str(item.get("id", index)) for index, item in enumerate(segments)]
        generate = post_json(
            api,
            f"/dub/generate/{job_id}",
            {
                "segments": [
                    {
                        "start": item["start"],
                        "end": item["end"],
                        "text": item["text"],
                        "target_lang": language,
                        "instruct": instruct,
                        "profile_id": _profile_for_segment(
                            item,
                            source_segments=source_segments,
                            clone_profiles=clone_profiles,
                            fallback_profile_id=fallback_profile_id,
                        ),
                        "effect_preset": "broadcast",
                    }
                    for item in segments
                ],
                "segment_ids": segment_ids,
                "language": language,
                "language_code": language_code,
                "instruct": instruct,
                "num_step": num_step,
                "guidance_scale": 2.0,
                "speed": 1.0,
                "slot_fit": "time_stretch",
                "timing_strategy": timing_strategy,
                "overflow_budget_s": 0.15,
            },
        )
        stream_task(
            api,
            generate["task_id"],
            logs_dir / "dub_generate.jsonl",
            completion_probe=lambda: _dub_track_info(api, job_id, language_code) is not None,
        )
        track_info = _dub_track_info(api, job_id, language_code)
    if track_info is None:
        raise RuntimeError(f"OmniVoice did not produce a {language_code!r} dubbed track for job {job_id}")
    export = get_json(
        api,
        f"/dub/download/{job_id}",
        {
            "preserve_bg": "true",
            "default_track": language_code,
            "include_tracks": language_code,
            "burn_subs": "false",
            "dual": "false",
            "save_path": str(dubbed_video.resolve()),
        },
    )
    manifest = {
        "job_id": job_id,
        "source_video": str(source_video),
        "project_dir": str(project_dir),
        "merged_srt": str(merged_srt),
        "merged_vtt": str(merged_vtt),
        "merged_segment_count": len(merged),
        "imported_segment_count": len(segments) if segments else None,
        "reused_existing_track": not bool(segments),
        "speaker_clone_profiles": clone_profiles or None,
        "source_voice_profile": source_voice_profile,
        "language": language,
        "language_code": language_code,
        "instruct": instruct,
        "num_step": num_step,
        "timing_strategy": timing_strategy,
        "omnivoice_track": track_info,
        "dubbed_video": str(dubbed_video),
        "export": export,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_explained_highlights(
    *,
    project_dir: Path,
    dubbed_video: Path,
    output_dir: Path,
    force: bool = False,
) -> Path:
    analysis = json.loads((project_dir / "assets" / "semantic_analysis.json").read_text(encoding="utf-8"))
    translated = json.loads((project_dir / "assets" / "translated_segments.json").read_text(encoding="utf-8"))["segments"]
    highlights = analysis.get("highlights", [])
    cards_dir = output_dir / "cards"
    card_pages_dir = output_dir / "card_pages"
    card_images_dir = output_dir / "card_images"
    clips_dir = output_dir / "clips"
    subtitles_dir = output_dir / "subtitles"
    logs_dir = output_dir / "logs"
    final_parts: list[Path] = []
    size = (1920, 1080)
    output = output_dir / "videos" / "semantic_highlights_explained_omnivoice.mp4"
    if output.exists() and output.stat().st_size > 0 and not force:
        return output
    opener = render_intro_html_card_video(
        output_html=card_pages_dir / "00_opening.html",
        output_image=card_images_dir / "00_opening.png",
        output_video=cards_dir / "00_opening.mp4",
        duration=3.4,
        size=size,
        log_file=logs_dir / "explained_highlights.log",
    )
    final_parts.append(opener)
    for index, item in enumerate(highlights, start=1):
        card_data = build_highlight_card(item, index=index)
        card = render_html_card_video(
            card=card_data,
            source_video=dubbed_video,
            output_html=card_pages_dir / f"{index:02}_reason.html",
            output_image=card_images_dir / f"{index:02}_reason.png",
            output_video=cards_dir / f"{index:02}_reason.mp4",
            duration=4.8,
            size=size,
            log_file=logs_dir / "explained_highlights.log",
        )
        start = card_data.start
        end = card_data.end
        raw_clip = render_clip(
            dubbed_video,
            clips_dir / f"{index:02}_dubbed_highlight_raw.mp4",
            start,
            end - start,
            log_file=logs_dir / "explained_highlights.log",
        )
        clip_srt = write_shifted_srt(
            subtitles_dir / f"{index:02}_dubbed_highlight.srt",
            translated,
            start=start,
            end=end,
        )
        clip = (
            burn_subtitles(
                raw_clip,
                clip_srt,
                clips_dir / f"{index:02}_dubbed_highlight.mp4",
                log_file=logs_dir / "explained_highlights.log",
            )
            if clip_srt.stat().st_size > 0
            else raw_clip
        )
        final_parts.extend([card, clip])
    concat_videos_reencode(final_parts, output, log_file=logs_dir / "explained_highlights.log")
    return output


def write_shifted_srt(path: Path, segments: list[dict[str, Any]], *, start: float, end: float) -> Path:
    cues: list[SpeechSegment] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        seg_start = float(segment.get("start", 0.0))
        seg_end = float(segment.get("end", seg_start))
        if seg_end <= start or seg_start >= end:
            continue
        cues.append(
            SpeechSegment(
                start=max(0.0, seg_start - start),
                end=max(0.05, min(end, seg_end) - start),
                text=text,
            )
        )
    return write_srt(path, cues)


def write_review_page(output_dir: Path, *, original_video: Path, dubbed_video: Path, explained_highlights: Path) -> Path:
    page = output_dir / "index.html"
    analysis_path = output_dir / "assets" / "omnivoice_dub_manifest.json"
    subtitle_vtt = output_dir / "assets" / "omnivoice_merged_zh.vtt"
    card_pages = sorted((output_dir / "card_pages").glob("*.html"))
    card_images = sorted((output_dir / "card_images").glob("*.png"))
    card_links = "\n".join(
        f'<a class="chip" href="{html.escape(os.path.relpath(path, output_dir))}">{html.escape(path.stem)}</a>'
        for path in card_pages
    )
    card_gallery = "\n".join(
        f'<a href="{html.escape(os.path.relpath(card_pages[index], output_dir)) if index < len(card_pages) else "#"}">'
        f'<img src="{html.escape(os.path.relpath(path, output_dir))}" alt="{html.escape(path.stem)}" /></a>'
        for index, path in enumerate(card_images)
    )
    original_display = _copy_reference_video(original_video, output_dir)
    subtitle_track_html = (
        f'<track kind="subtitles" srclang="zh" label="中文字幕" default src="{html.escape(os.path.relpath(subtitle_vtt, output_dir))}" />'
        if subtitle_vtt.exists()
        else ""
    )
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LogicCut OmniVoice 配音优化版</title>
  <style>
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK SC","Microsoft YaHei",sans-serif; color:#17221b; background:#fbfcf8; line-height:1.58; }}
    header, section {{ border-bottom:1px solid #d9e1da; }}
    .wrap {{ width:min(1180px, calc(100vw - 40px)); margin:0 auto; padding:30px 0; }}
    header {{ background:#edf5ef; }}
    h1 {{ margin:0 0 10px; font-size:32px; letter-spacing:0; }}
    h2 {{ margin:0 0 16px; font-size:22px; letter-spacing:0; }}
    .grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:18px; }}
    .panel {{ border:1px solid #d9e1da; border-radius:8px; background:#fff; overflow:hidden; }}
    .body {{ padding:15px; }}
    video {{ display:block; width:100%; background:#111; aspect-ratio:16/9; }}
    p {{ margin:0 0 10px; }}
    .meta {{ color:#607067; font-size:14px; }}
    a {{ color:#285ea8; font-weight:600; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid #d9e1da; }}
    th,td {{ padding:11px 12px; border-bottom:1px solid #d9e1da; text-align:left; vertical-align:top; font-size:14px; }}
    th {{ background:#edf3ec; }}
    code {{ background:#eef2ee; border:1px solid #dde5de; border-radius:5px; padding:1px 5px; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:10px; }}
    .chip {{ display:inline-flex; align-items:center; min-height:34px; padding:5px 13px; border:1px solid #d3dfd7; border-radius:999px; background:#fff; color:#24505b; font-size:14px; }}
    .thumbs {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin-top:16px; }}
    .thumbs img {{ display:block; width:100%; aspect-ratio:16/9; object-fit:cover; border:1px solid #d9e1da; border-radius:8px; background:#fff; }}
    @media (max-width: 920px) {{ .grid {{ grid-template-columns:1fr; }} .wrap {{ width:calc(100vw - 24px); }} }}
    @media (max-width: 920px) {{ .thumbs {{ grid-template-columns:1fr 1fr; }} }}
  </style>
</head>
<body>
  <header><div class="wrap">
    <h1>LogicCut OmniVoice 配音优化版</h1>
    <p>这版不再把配音手工外挂，而是复用 OmniVoice Studio 的 dubbing pipeline：先从原视频分离人声并裁出 job-scoped speaker clone，再导入中文字幕分段，调用 <code>dub/generate</code> 做分段配音、时长适配和音轨拼接，最后通过 <code>dub/download</code> 快速导出中文默认音轨视频。</p>
    <p class="meta">全量视频使用 VTT 字幕轨，避免 29 分钟 AV1 视频整段烧字幕导致超时；高光剪辑较短，已把中文字幕烧录进画面。</p>
  </div></header>
  <section><div class="wrap">
    <h2>可验收视频</h2>
    <div class="grid">
      <article class="panel"><video controls preload="metadata" src="{html.escape(os.path.relpath(original_display, output_dir))}"></video><div class="body"><strong>原作</strong><p class="meta">下载自 YouTube，用于对照，已复制到当前验收目录。</p></div></article>
      <article class="panel"><video controls preload="metadata" src="{html.escape(os.path.relpath(dubbed_video, output_dir))}">{subtitle_track_html}</video><div class="body"><strong>OmniVoice 中文配音版</strong><p class="meta">中文配音由 OmniVoice 生成并混入背景音；中文字幕以 VTT 字幕轨默认加载。</p></div></article>
      <article class="panel"><video controls preload="metadata" src="{html.escape(os.path.relpath(explained_highlights, output_dir))}"></video><div class="body"><strong>解释型高光剪辑</strong><p class="meta">每个高光前加入 Codex 生成的 HTML 网页卡片，片段来自配音版并保留中文字幕。</p></div></article>
    </div>
  </div></section>
  <section><div class="wrap">
    <h2>处理说明</h2>
    <table>
      <tr><th>步骤</th><th>实现</th></tr>
      <tr><td>音色</td><td>OmniVoice 准备阶段从 <code>vocals.wav</code> 裁出 <code>voice_speaker_*.wav</code>；LogicCut 生成时优先传入 <code>profile_id=auto:speaker_*</code>。<code>男，中年，中音调</code> 只是没有 auto clone 时的兜底风格。</td></tr>
      <tr><td>分段</td><td>复用 LogicCut 已有中文翻译，合并为适合配音的长段，再导入 OmniVoice <code>/dub/import-srt</code>。</td></tr>
      <tr><td>配音</td><td>调用 OmniVoice <code>/dub/generate</code>，保留其时长适配、分段 wav 写入和完整中文音轨拼接逻辑。</td></tr>
      <tr><td>导出</td><td>调用 OmniVoice <code>/dub/download</code>，默认中文音轨，保留背景音，视频流走快速 copy，字幕以 <code>omnivoice_merged_zh.vtt</code> 提供。</td></tr>
      <tr><td>高光</td><td>按 Gemini 选出的 4 个语义高光切片；每段前生成一个独立 HTML 小网页卡片，并对高光片段烧录中文字幕。</td></tr>
    </table>
    <p class="meta">运行 manifest：<a href="{html.escape(os.path.relpath(analysis_path, output_dir))}">omnivoice_dub_manifest.json</a></p>
    <p class="meta">字幕轨：<a href="{html.escape(os.path.relpath(subtitle_vtt, output_dir))}">omnivoice_merged_zh.vtt</a></p>
    <p class="meta">高光 HTML 卡片：</p>
    <div class="chips">{card_links}</div>
    <div class="thumbs">{card_gallery}</div>
  </div></section>
</body>
</html>
"""
    page.write_text(html_text, encoding="utf-8")
    return page


def _copy_reference_video(original_video: Path, output_dir: Path) -> Path:
    destination = output_dir / "videos" / f"original_{original_video.name}"
    if destination.resolve() == original_video.resolve():
        return original_video
    if not destination.exists() or destination.stat().st_size != original_video.stat().st_size:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original_video, destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drive OmniVoice Studio dubbing from a LogicCut semantic project.")
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("--source-video", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--api", default="http://127.0.0.1:3901")
    parser.add_argument("--job-id", default="logiccut_yt_karpathy_zh")
    parser.add_argument("--max-duration", type=float, default=18.0)
    parser.add_argument("--max-chars", type=int, default=220)
    parser.add_argument("--language", default="Chinese")
    parser.add_argument("--language-code", default="zh")
    parser.add_argument("--instruct", default="男，中年，中音调")
    parser.add_argument("--num-step", type=int, default=8)
    parser.add_argument("--timing-strategy", choices=("concise", "strict_slot", "stretch_video"), default="strict_slot")
    parser.add_argument("--force-highlights", action="store_true", help="Rebuild HTML cards, clips, subtitles, and final highlight video.")
    args = parser.parse_args(argv)

    manifest = run_dub_pipeline(
        api=args.api,
        source_video=args.source_video.resolve(),
        project_dir=args.project_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        job_id=args.job_id,
        max_duration=args.max_duration,
        max_chars=args.max_chars,
        language=args.language,
        language_code=args.language_code,
        instruct=args.instruct,
        num_step=args.num_step,
        timing_strategy=args.timing_strategy,
    )
    dubbed_video = Path(manifest["dubbed_video"])
    explained = build_explained_highlights(
        project_dir=args.project_dir.resolve(),
        dubbed_video=dubbed_video,
        output_dir=args.output_dir.resolve(),
        force=args.force_highlights,
    )
    page = write_review_page(
        args.output_dir.resolve(),
        original_video=args.source_video.resolve(),
        dubbed_video=dubbed_video,
        explained_highlights=explained,
    )
    result = {
        **manifest,
        "explained_highlights": str(explained),
        "review_page": str(page),
        "dubbed_duration": ffprobe_duration(dubbed_video),
        "explained_highlights_duration": ffprobe_duration(explained),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
