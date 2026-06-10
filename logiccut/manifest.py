from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.2"
MANIFEST_NAME = "project.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def relpath(path: Path, start: Path) -> str:
    return os.path.relpath(path.resolve(), start.resolve())


def create_manifest(project_dir: Path, input_path: Path, title: str | None = None) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    input_path = input_path.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "title": title or input_path.stem,
        "created_at": now,
        "updated_at": now,
        "input": {
            "path": relpath(input_path, project_dir),
            "kind": "video",
            "source": "local",
        },
        "transcripts": [],
        "speakers": [],
        "tracks": [],
        "clips": [],
        "timeline": [],
        "style": {
            "subtitle": "subcap-ass-captioner",
            "layout": "source",
            "voice": "source",
        },
        "renders": [],
        "recipes": [],
        "logs": [],
    }


def manifest_path(project_dir: Path) -> Path:
    return project_dir / MANIFEST_NAME


def load_manifest(project_dir: Path) -> dict[str, Any]:
    path = manifest_path(project_dir)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_manifest(project_dir: Path, manifest: dict[str, Any]) -> Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    manifest["updated_at"] = utc_now()
    path = manifest_path(project_dir)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def upsert_by_id(items: list[dict[str, Any]], item: dict[str, Any]) -> None:
    item_id = item["id"]
    for idx, existing in enumerate(items):
        if existing.get("id") == item_id:
            items[idx] = item
            return
    items.append(item)


def append_log(manifest: dict[str, Any], event: str, message: str, **extra: Any) -> None:
    entry: dict[str, Any] = {
        "time": utc_now(),
        "event": event,
        "message": message,
    }
    entry.update(extra)
    manifest.setdefault("logs", []).append(entry)
