from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

from .html_cards import HighlightCard
from .media import ffprobe_duration, ffprobe_video_size, run_command, subtitle_font_name, write_srt
from .subtitles import ffmpeg_ass_filter, write_ass_from_srt
from .text_normalize import normalize_display_text
from .tts_engines import resolve_tts_engine


def build_narration_text(card: HighlightCard, *, max_chars: int = 86) -> str:
    title = _clean_text(card.title)
    hook = _clean_text(card.hook)
    reason = _clean_text(card.reason)
    parts = [f"这一章先看：{title}。"]
    if hook:
        parts.append(f"重点是，{_strip_sentence_end(hook)}。")
    if reason and reason != hook:
        parts.append(f"我把它放在这里，是因为{_strip_sentence_end(reason)}。")
    text = " ".join(parts)
    return _limit_text(text, max_chars=max_chars)


def write_narration_srt(path: Path, text: str, *, duration: float) -> Path:
    clean = normalize_display_text(text)
    cue_texts = _split_narration_cues(clean)
    safe_duration = max(duration, 0.5)
    if not cue_texts:
        cue_texts = [clean or " "]
    total_weight = sum(max(len(item.replace("\n", "")), 1) for item in cue_texts)
    cursor = 0.0
    segments: list[dict[str, object]] = []
    for index, cue_text in enumerate(cue_texts):
        if index == len(cue_texts) - 1:
            cue_end = safe_duration
        else:
            weight = max(len(cue_text.replace("\n", "")), 1)
            cue_end = min(safe_duration, cursor + safe_duration * weight / max(total_weight, 1))
        segments.append({"start": round(cursor, 3), "end": round(max(cue_end, cursor + 0.1), 3), "text": cue_text})
        cursor = cue_end
    return write_srt(path, segments)


def prepare_narration_reference(
    source_video: Path,
    output_path: Path,
    *,
    start: float,
    end: float,
    min_duration: float = 4.0,
    max_duration: float = 12.0,
    log_file: Path | None = None,
) -> Path:
    output_path = output_path.expanduser().resolve()
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    duration = min(max_duration, max(min_duration, end - start))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{max(start, 0.0):.3f}",
            "-i",
            str(source_video),
            "-t",
            f"{duration:.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "24000",
            "-af",
            "loudnorm=I=-20:TP=-2:LRA=11",
            str(output_path),
        ],
        log_file=log_file,
    )
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"failed to extract narration reference audio: {output_path}")
    return output_path


def synthesize_narration_audio(
    text: str,
    output_path: Path,
    *,
    engine: str | None = None,
    voice: str | None = None,
    tts_ports: str | None = None,
    backend_options: dict[str, Any] | None = None,
    timeout_s: int | None = None,
    log_file: Path | None = None,
) -> dict[str, Any]:
    clean = _clean_text(text)
    if not clean:
        raise ValueError("narration text must not be empty")
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selected_engine = engine or os.environ.get("LOGICCUT_NARRATION_TTS_ENGINE") or "indextts2"
    selected_voice = voice or os.environ.get("LOGICCUT_NARRATION_VOICE") or "logiccut-narrator"
    preset = resolve_tts_engine(selected_engine, tts_ports=tts_ports)
    endpoint = _tts_endpoint(preset.tts_ports, preset.fish_tts_adapter_url)
    raw_options = dict(backend_options or {})
    ref_wav = str(raw_options.pop("ref_wav", "") or os.environ.get("LOGICCUT_NARRATION_REF_WAV", "")).strip()
    ref_text = str(raw_options.pop("ref_text", "") or os.environ.get("LOGICCUT_NARRATION_REF_TEXT", "")).strip()
    language = str(raw_options.pop("language", "") or os.environ.get("LOGICCUT_NARRATION_LANGUAGE", "zh-CN")).strip()
    options = {
        "purpose": "chapter_card_narration",
        "voice_role": selected_voice,
        "language": language,
    }
    options.update(raw_options)
    payload: dict[str, Any] = {
        "text": clean,
        "output_path": str(output_path),
        "voice_role": selected_voice,
        "backend_options": options,
    }
    if ref_wav:
        payload["ref_wav"] = ref_wav
    if ref_text:
        payload["ref_text"] = ref_text
    if language:
        payload["language"] = language
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(
                "chapter_narration.tts "
                + json.dumps(
                    {
                        "endpoint": endpoint,
                        "engine": preset.engine,
                        "voice": selected_voice,
                        "chars": len(clean),
                        "output_path": str(output_path),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    result = _post_json(
        endpoint,
        payload,
        timeout_s=timeout_s or int(os.environ.get("LOGICCUT_NARRATION_TTS_TIMEOUT", "300")),
    )
    if not result.get("success", True):
        raise RuntimeError(f"narration TTS failed: {result}")
    if not output_path.exists() or output_path.stat().st_size == 0:
        returned = Path(str(result.get("output_path") or output_path))
        if returned.exists() and returned != output_path:
            output_path.write_bytes(returned.read_bytes())
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"narration TTS did not create audio: {output_path}")
    return {
        **result,
        "backend": result.get("backend") or preset.engine,
        "engine": preset.engine,
        "voice": selected_voice,
        "output_path": str(output_path),
    }


def mix_card_with_narration(
    card_video: Path,
    narration_audio: Path,
    subtitle_path: Path,
    output_path: Path,
    *,
    narration_db: float = 0.0,
    log_file: Path | None = None,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = ffprobe_video_size(card_video)
    ass_path = subtitle_path.with_suffix(".ass") if subtitle_path.suffix.lower() != ".ass" else subtitle_path
    if subtitle_path.suffix.lower() != ".ass":
        preset = os.environ.get(
            "LOGICCUT_NARRATION_SUBTITLE_STYLE",
            os.environ.get("LOGICCUT_SUBTITLE_STYLE", "captioner"),
        )
        max_chars_env = os.environ.get("LOGICCUT_NARRATION_SUBTITLE_MAX_CHARS")
        write_ass_from_srt(
            subtitle_path,
            ass_path,
            width=width,
            height=height,
            preset=preset,
            font_name=subtitle_font_name(),
            position=os.environ.get("LOGICCUT_NARRATION_SUBTITLE_POSITION", "bottom"),
            max_chars=int(max_chars_env) if max_chars_env else None,
        )
    subtitle_filter = ffmpeg_ass_filter(ass_path)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(card_video),
            "-i",
            str(narration_audio),
            "-vf",
            subtitle_filter,
            "-filter_complex",
            f"[1:a:0]volume={_volume_expr(narration_db)},apad[a]",
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        log_file=log_file,
    )
    return output_path


def _split_narration_cues(text: str, *, max_line_chars: int = 20, max_lines: int = 2) -> list[str]:
    clean = normalize_display_text(text)
    max_chars = max_line_chars * max_lines
    parts = _sentence_parts(clean)
    raw_chunks: list[str] = []
    current = ""
    for part in parts:
        if len(part) > max_chars:
            if current:
                raw_chunks.append(current)
                current = ""
            raw_chunks.extend(_split_long_part(part, max_chars))
            continue
        if current and len(current + part) > max_chars:
            raw_chunks.append(current)
            current = part
        else:
            current += part
    if current:
        raw_chunks.append(current)
    cues: list[str] = []
    for chunk in raw_chunks:
        lines = _wrap_subtitle_lines(chunk, max_line_chars=max_line_chars)
        for index in range(0, len(lines), max_lines):
            cues.append("\n".join(lines[index : index + max_lines]))
    return [cue for cue in cues if cue.strip()]


def _sentence_parts(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", normalize_display_text(text))
    return re.findall(r"[^。！？!?；;，,、]+[。！？!?；;，,、]?", compact) or ([compact] if compact else [])


def _split_long_part(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]


def _wrap_subtitle_text(text: str, *, max_line_chars: int, max_lines: int) -> str:
    lines = _wrap_subtitle_lines(text, max_line_chars=max_line_chars)
    return "\n".join(lines[:max_lines])


def _wrap_subtitle_lines(text: str, *, max_line_chars: int) -> list[str]:
    if len(text) <= max_line_chars:
        return [text]
    lines: list[str] = []
    rest = text
    while rest:
        if len(rest) <= max_line_chars:
            lines.append(rest)
            break
        split_at = _subtitle_split_index(rest, max_line_chars)
        lines.append(rest[:split_at])
        rest = rest[split_at:]
    return lines


def _subtitle_split_index(text: str, max_line_chars: int) -> int:
    candidates = "，,、；;。！？!?—：:"
    lower = max(8, int(max_line_chars * 0.55))
    upper = min(len(text), max_line_chars)
    for index in range(upper, lower - 1, -1):
        if text[index - 1] in candidates:
            return index
    return upper


def safe_audio_duration(path: Path, *, fallback: float) -> float:
    try:
        duration = ffprobe_duration(path)
    except Exception:
        return fallback
    return duration if duration > 0 else fallback


def _tts_endpoint(tts_ports: str | None, adapter_url: str | None) -> str:
    explicit = os.environ.get("LOGICCUT_NARRATION_TTS_URL")
    if explicit:
        return _ensure_tts_path(explicit)
    if tts_ports:
        port = str(tts_ports).split(",")[0].strip()
        if port:
            return f"http://127.0.0.1:{port}/tts"
    if adapter_url:
        return _ensure_tts_path(adapter_url)
    raise ValueError("narration TTS endpoint is not configured")


def _ensure_tts_path(url: str) -> str:
    clean = url.rstrip("/")
    if clean.endswith("/tts"):
        return clean
    return clean + "/tts"


def _post_json(url: str, payload: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        raw = response.read().decode("utf-8")
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        raise RuntimeError(f"narration TTS response must be a JSON object: {data!r}")
    return data


def _clean_text(value: str) -> str:
    return normalize_display_text(value)


def _strip_sentence_end(value: str) -> str:
    return value.rstrip("。！？.!?；;，, ")


def _limit_text(text: str, *, max_chars: int) -> str:
    clean = _clean_text(text)
    if len(clean) <= max_chars:
        return clean
    clipped = clean[: max(1, max_chars - 1)].rstrip("，。,. ")
    return clipped + "。"


def _volume_expr(db: float) -> str:
    if db == 0:
        return "1.0"
    return f"{10 ** (db / 20):.6f}"
