from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DownloadResult:
    url: str
    path: Path
    metadata: dict[str, Any]
    bytes: int


def build_ytdlp_command(
    url: str,
    output_dir: Path,
    *,
    prefix: str | None = None,
    cookies: Path | None = None,
) -> list[str]:
    output_dir = output_dir.resolve()
    filename = sanitize_filename(prefix or "%(title).120s-%(id)s")
    output_template = str(output_dir / f"{filename}.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--restrict-filenames",
        "--merge-output-format",
        "mp4",
        "-f",
        "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "-o",
        output_template,
        "--print",
        "%()j",
        "--print",
        "after_move:filepath",
    ]
    if cookies:
        cmd.extend(["--cookies", str(cookies.expanduser().resolve())])
    if is_bilibili_url(url):
        cmd.extend(
            [
                "--add-header",
                "Referer:https://www.bilibili.com",
                "--add-header",
                (
                    "User-Agent:Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
                ),
            ]
        )
    cmd.append(url)
    return cmd


def download_video(
    url: str,
    output_dir: Path,
    *,
    prefix: str | None = None,
    cookies: Path | None = None,
) -> DownloadResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_ytdlp_command(url, output_dir, prefix=prefix, cookies=cookies)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed ({proc.returncode}): {proc.stderr.strip()}")

    metadata, filepath = parse_ytdlp_stdout(proc.stdout)
    path = Path(filepath).expanduser().resolve()
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"yt-dlp did not produce a video file: {path}")

    result = DownloadResult(
        url=url,
        path=path,
        metadata=metadata,
        bytes=path.stat().st_size,
    )
    write_download_manifest(output_dir / "download.json", result)
    return result


def parse_ytdlp_stdout(stdout: str) -> tuple[dict[str, Any], str]:
    metadata: dict[str, Any] | None = None
    filepath = ""
    for line in stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("{") and text.endswith("}"):
            metadata = json.loads(text)
        else:
            filepath = text
    if metadata is None:
        raise RuntimeError("yt-dlp did not print metadata JSON")
    if not filepath:
        raise RuntimeError("yt-dlp did not print the final filepath")
    return metadata, filepath


def write_download_manifest(path: Path, result: DownloadResult) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "url": result.url,
        "path": str(result.path),
        "bytes": result.bytes,
        "metadata": {
            "id": result.metadata.get("id"),
            "title": result.metadata.get("title"),
            "webpage_url": result.metadata.get("webpage_url"),
            "duration": result.metadata.get("duration"),
            "extractor_key": result.metadata.get("extractor_key"),
            "channel": result.metadata.get("channel"),
            "uploader": result.metadata.get("uploader"),
        },
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def sanitize_filename(value: str) -> str:
    if "%(" in value:
        return value
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    text = text.strip(".-_")
    return text or "download"


def is_bilibili_url(url: str) -> bool:
    return "bilibili.com" in str(url).lower() or "b23.tv" in str(url).lower()
