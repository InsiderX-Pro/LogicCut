from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TEMPLATE_ROOT = Path(__file__).resolve().parent / "card_templates"


@dataclass(frozen=True)
class CardTemplate:
    id: str
    name: str
    description: str
    template_path: Path
    aspect_ratios: tuple[str, ...]
    max_title_chars: int
    template_pack: str
    source_type: str
    origin_repo: str
    origin_license: str
    adaptation_notes: str


def list_card_templates() -> list[CardTemplate]:
    templates: list[CardTemplate] = []
    if not TEMPLATE_ROOT.exists():
        return templates
    for manifest_path in sorted(TEMPLATE_ROOT.glob("*/manifest.json")):
        templates.append(_load_manifest(manifest_path))
    return templates


def get_card_template(template_id: str | None) -> CardTemplate:
    selected = (template_id or "news-hook").strip() or "news-hook"
    manifest_path = TEMPLATE_ROOT / selected / "manifest.json"
    if not manifest_path.exists():
        known = ", ".join(template.id for template in list_card_templates()) or "none"
        raise ValueError(f"unknown card template: {selected}. Available templates: {known}")
    return _load_manifest(manifest_path)


def render_template_html(template_id: str | None, values: dict[str, Any]) -> str:
    template = get_card_template(template_id)
    source = template.template_path.read_text(encoding="utf-8")
    merged = {
        "common_css": _common_css(),
        "template_id": template.id,
        "template_name": template.name,
        **values,
    }
    html = source
    for key, value in merged.items():
        html = html.replace("{{" + key + "}}", str(value))
    unresolved = sorted(set(re.findall(r"{{\s*([A-Za-z0-9_-]+)\s*}}", html)))
    if unresolved:
        raise ValueError(f"unresolved card template placeholders in {template.id}: {', '.join(unresolved)}")
    return html


def _load_manifest(path: Path) -> CardTemplate:
    data = json.loads(path.read_text(encoding="utf-8"))
    template_path = path.parent / str(data.get("template", "template.html"))
    if not template_path.exists():
        raise ValueError(f"card template file is missing: {template_path}")
    return CardTemplate(
        id=str(data["id"]),
        name=str(data.get("name") or data["id"]),
        description=str(data.get("description") or ""),
        template_path=template_path,
        aspect_ratios=tuple(data.get("aspect_ratios") or ("16:9",)),
        max_title_chars=int(data.get("max_title_chars") or 40),
        template_pack=str(data.get("template_pack") or "logiccut-native"),
        source_type=str(data.get("source_type") or "native"),
        origin_repo=str(data.get("origin_repo") or "LogicCut"),
        origin_license=str(data.get("origin_license") or "project"),
        adaptation_notes=str(data.get("adaptation_notes") or "Native LogicCut HTML card template."),
    )


def _common_css() -> str:
    path = TEMPLATE_ROOT / "common.css"
    return path.read_text(encoding="utf-8") if path.exists() else ""
