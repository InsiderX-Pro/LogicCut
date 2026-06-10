#!/usr/bin/env python3
from __future__ import annotations

import argparse
from hashlib import sha1
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from huggingface_hub import HfApi, scan_cache_dir, snapshot_download


def load_model_config(root: Path) -> dict:
    return json.loads((root / "configs" / "models.json").read_text(encoding="utf-8"))


def cache_snapshot(repo_id: str, cache_dir: str | None) -> dict | None:
    try:
        info = scan_cache_dir(cache_dir)
    except Exception:
        return None
    for repo in info.repos:
        if repo.repo_id == repo_id and repo.size_on_disk > 0:
            return {
                "repo_id": repo.repo_id,
                "size_on_disk": repo.size_on_disk,
                "nb_files": repo.nb_files,
            }
    return None


def audioseal_cache_dir() -> Path:
    base = os.environ.get("AUDIOSEAL_CACHE_DIR") or os.environ.get("XDG_CACHE_HOME") or "~/.cache"
    return Path(base).expanduser().resolve() / "audioseal"


def audioseal_filename(url: str) -> str:
    return sha1(urlparse(url).path.encode()).hexdigest()[:24]


def audioseal_status(model: dict) -> dict:
    cache_dir = audioseal_cache_dir()
    files = []
    size = 0
    for url in model.get("files", []):
        path = cache_dir / audioseal_filename(url)
        exists = path.exists() and path.stat().st_size > 0
        if exists:
            size += path.stat().st_size
        files.append({"url": url, "path": str(path), "exists": exists})
    return {
        "cache_dir": str(cache_dir),
        "files": files,
        "size_on_disk": size,
        "nb_files": sum(1 for item in files if item["exists"]),
        "complete": bool(files) and all(item["exists"] for item in files),
    }


def download_audioseal(model: dict, local_files_only: bool) -> dict:
    status = audioseal_status(model)
    if status["complete"]:
        return {"status": "cached", **status}
    if local_files_only:
        return {"status": "failed", "error": "AudioSeal files are not cached", **status}

    import torch

    cache_dir = audioseal_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    for url in model.get("files", []):
        torch.hub.load_state_dict_from_url(
            url,
            model_dir=str(cache_dir),
            map_location="cpu",
            file_name=audioseal_filename(url),
        )
    status = audioseal_status(model)
    return {"status": "downloaded" if status["complete"] else "failed", **status}


def resolve_models(config: dict, include_gated: bool, include_isolated: bool) -> list[dict]:
    models = list(config["default"])
    if include_gated:
        models.extend(config.get("gated_optional", []))
    if include_isolated:
        models.extend(config.get("isolated_optional", []))
    return models


def main() -> int:
    parser = argparse.ArgumentParser(description="Download LogicCut local model weights.")
    parser.add_argument("--include-gated", action="store_true", help="also download gated models when HF_TOKEN is set")
    parser.add_argument("--include-isolated", action="store_true", help="also download isolated optional engine weights")
    parser.add_argument("--local-files-only", action="store_true", help="only verify existing local cache")
    parser.add_argument("--report", default=None, help="write JSON report path")
    args = parser.parse_args()

    root = Path(os.environ.get("LOGICCUT_ROOT", Path(__file__).resolve().parents[1]))
    cache_dir = os.environ.get("HF_HUB_CACHE")
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
    config = load_model_config(root)

    report = {
        "root": str(root),
        "hf_home": os.environ.get("HF_HOME"),
        "hf_hub_cache": cache_dir,
        "local_files_only": args.local_files_only,
        "items": [],
    }

    models = resolve_models(config, args.include_gated, args.include_isolated)
    api = HfApi(token=token)
    for model in models:
        repo_id = model["repo_id"]
        item = {**model, "status": "pending"}
        if model.get("cache_type") == "audioseal":
            started = time.time()
            result = download_audioseal(model, args.local_files_only)
            item.update(result)
            item["seconds"] = round(time.time() - started, 2)
            report["items"].append(item)
            print(f"[{item['status']}] {repo_id}: {item.get('size_on_disk', 0)} bytes")
            continue

        requires_env = model.get("requires_env")
        if requires_env and not os.environ.get(requires_env):
            item["status"] = "skipped"
            item["reason"] = f"{requires_env} is not set or model license has not been accepted"
            report["items"].append(item)
            print(f"[skip] {repo_id}: {item['reason']}")
            continue

        cached = cache_snapshot(repo_id, cache_dir)
        if cached:
            item.update(cached)
            item["status"] = "cached"
            report["items"].append(item)
            print(f"[ok] {repo_id}: cached ({cached['size_on_disk']} bytes)")
            continue

        started = time.time()
        try:
            # A lightweight auth/provenance check gives clearer errors for gated
            # repos before a multi-GB download begins.
            if not args.local_files_only:
                api.model_info(repo_id, token=token)
            path = snapshot_download(
                repo_id=repo_id,
                revision=model.get("revision"),
                cache_dir=cache_dir,
                token=token,
                local_files_only=args.local_files_only,
            )
            cached = cache_snapshot(repo_id, cache_dir) or {}
            item.update(cached)
            item["status"] = "downloaded" if not args.local_files_only else "cached"
            item["path"] = path
            item["seconds"] = round(time.time() - started, 2)
            print(f"[ok] {repo_id}: {item['status']} -> {path}")
        except Exception as exc:
            item["status"] = "failed"
            item["error"] = str(exc)
            print(f"[fail] {repo_id}: {exc}", file=sys.stderr)
        report["items"].append(item)

    report_path = Path(args.report or root / "logs" / "model-download-report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[report] {report_path}")
    return 1 if any(item["status"] == "failed" for item in report["items"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
