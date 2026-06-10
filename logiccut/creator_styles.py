from __future__ import annotations

from dataclasses import dataclass

from .html_cards import HighlightCard
from .text_normalize import normalize_display_text


@dataclass(frozen=True)
class CreatorStyle:
    id: str
    name: str
    tone: str
    narration_pattern: str
    report_frame: str
    template_sequence: tuple[str, ...]


STYLE_ALIASES = {
    "冷静": "calm",
    "calm": "calm",
    "犀利": "sharp",
    "sharp": "sharp",
    "科普": "science",
    "science": "science",
    "explainer": "science",
    "娱乐": "entertainment",
    "entertainment": "entertainment",
    "fun": "entertainment",
}


CREATOR_STYLES: dict[str, CreatorStyle] = {
    "calm": CreatorStyle(
        id="calm",
        name="冷静分析",
        tone="克制、清楚、结论先行，不夸张煽动。",
        narration_pattern="{catchphrase}我们冷静看这一段：{title}。它的价值是{reason}。",
        report_frame="用低情绪密度的方式先建立判断，让观众理解这段为什么值得看。",
        template_sequence=("timeline-chapter", "data-insight", "news-hook"),
    ),
    "sharp": CreatorStyle(
        id="sharp",
        name="犀利评论",
        tone="直接、带判断、有锋芒，先抛冲突。",
        narration_pattern="{catchphrase}这段先别温吞：{hook}。它够尖锐，因为{reason}。",
        report_frame="先把矛盾和判断抛出来，形成评论型账号需要的冲突入口。",
        template_sequence=("conflict-card", "news-hook", "quote-focus"),
    ),
    "science": CreatorStyle(
        id="science",
        name="科普解释",
        tone="解释概念、补上下文、让复杂内容更容易懂。",
        narration_pattern="{catchphrase}这里先补一个背景：{title}。它能解释{hook}，所以适合作为这一章入口。",
        report_frame="把片段当成概念解释节点，先补背景，再进入原视频内容。",
        template_sequence=("data-insight", "timeline-chapter", "news-hook"),
    ),
    "entertainment": CreatorStyle(
        id="entertainment",
        name="娱乐吐槽",
        tone="轻松、有梗、节奏快，降低理解门槛。",
        narration_pattern="{catchphrase}先别划走，这段有梗：{hook}。好看点是{reason}。",
        report_frame="先用轻松的入口降低门槛，再把观点包进高光片段。",
        template_sequence=("vertical-hook", "quote-focus", "conflict-card"),
    ),
}


def get_creator_style(style_id: str | None) -> CreatorStyle:
    normalized = _normalize_style_id(style_id or "calm")
    if normalized not in CREATOR_STYLES:
        known = ", ".join(CREATOR_STYLES)
        raise ValueError(f"unknown creator style: {style_id}. Available styles: {known}")
    return CREATOR_STYLES[normalized]


def parse_style_ids(raw: str | None) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return ("calm", "sharp", "science", "entertainment")
    styles: list[str] = []
    for item in raw.replace("，", ",").split(","):
        if not item.strip():
            continue
        style_id = _normalize_style_id(item)
        if style_id not in styles:
            styles.append(style_id)
    return tuple(styles or ("calm", "sharp", "science", "entertainment"))


def parse_layouts(raw: str | None) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return ("landscape", "portrait")
    aliases = {
        "landscape": "landscape",
        "horizontal": "landscape",
        "横屏": "landscape",
        "portrait": "portrait",
        "vertical": "portrait",
        "竖屏": "portrait",
    }
    layouts: list[str] = []
    for item in raw.replace("，", ",").split(","):
        normalized = aliases.get(item.strip().lower(), item.strip().lower())
        if normalized not in {"landscape", "portrait"}:
            raise ValueError(f"unknown personalized layout: {item}")
        if normalized not in layouts:
            layouts.append(normalized)
    return tuple(layouts or ("landscape", "portrait"))


def parse_catchphrases(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    phrases: list[str] = []
    for item in raw.replace("，", ",").split(","):
        phrase = normalize_display_text(item).strip(" ，,。.")
        if phrase:
            phrases.append(phrase)
    return tuple(phrases)


def build_personalized_narration(
    card: HighlightCard,
    style: CreatorStyle,
    *,
    catchphrases: tuple[str, ...] = (),
    max_chars: int = 118,
) -> str:
    catchphrase = f"{catchphrases[(card.index - 1) % len(catchphrases)]}，" if catchphrases else ""
    raw_hook = _strip_sentence_end(card.hook or card.title)
    raw_reason = _strip_sentence_end(card.reason or raw_hook)
    hook = _fallback_hook(style.id, card.title) if len(raw_hook) > 48 else _short_clause(raw_hook, 42)
    reason = _fallback_reason(style.id) if len(raw_reason) > 62 else _short_clause(raw_reason, 44)
    if hook and reason and (reason.startswith(hook[: min(len(hook), 12)]) or hook.startswith(reason[: min(len(reason), 12)])):
        reason = _fallback_reason(style.id)
    text = style.narration_pattern.format(
        catchphrase=catchphrase,
        title=_short_clause(card.title, 36),
        hook=hook,
        reason=reason,
    )
    return _limit_text(normalize_display_text(text), max_chars=max_chars)


def build_cut_explanation(
    card: HighlightCard,
    style: CreatorStyle,
    *,
    narration_text: str,
    layout: str,
    template_id: str,
    reference_audio: str | None,
    catchphrases: tuple[str, ...],
) -> dict[str, object]:
    return {
        "chapter_index": card.index,
        "title": card.title,
        "start": card.start,
        "end": card.end,
        "score": card.score,
        "style_id": style.id,
        "style_name": style.name,
        "tone": style.tone,
        "layout": layout,
        "template_id": template_id,
        "why_this_clip": card.reason,
        "hook": card.hook,
        "narration_text": narration_text,
        "cut_strategy": style.report_frame,
        "reference_audio": reference_audio,
        "catchphrases": list(catchphrases),
    }


def _normalize_style_id(value: str | None) -> str:
    key = normalize_display_text(value or "").strip().lower()
    return STYLE_ALIASES.get(key, key)


def _strip_sentence_end(text: str) -> str:
    return normalize_display_text(text).strip().rstrip("。！？!?；;，,、")


def _short_clause(text: str, max_chars: int) -> str:
    clean = _strip_sentence_end(text)
    if len(clean) <= max_chars:
        return clean
    breakpoints = "，,；;、。！？!?"
    lower = max(12, int(max_chars * 0.55))
    for index in range(min(len(clean), max_chars), lower, -1):
        if clean[index - 1] in breakpoints:
            return _strip_sentence_end(clean[:index])
    return clean[:max_chars].rstrip("，,；;、 ")


def _fallback_hook(style_id: str, title: str) -> str:
    clean_title = _short_clause(title, 28)
    if "AI" in clean_title or "模型" in clean_title:
        return "AI一边像天才，一边又犯低级错误"
    if style_id == "entertainment":
        return f"{clean_title}这个反差很抓人"
    return clean_title


def _fallback_reason(style_id: str) -> str:
    if style_id == "sharp":
        return "它把 AI 的强弱反差讲得特别直观"
    if style_id == "science":
        return "它能把锯齿状智能这个概念讲清楚"
    if style_id == "entertainment":
        return "这个反差荒谬又好笑，观众容易看懂"
    return "它用一个例子讲清楚 AI 能力的反差"


def _limit_text(text: str, *, max_chars: int) -> str:
    clean = normalize_display_text(text).strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max(0, max_chars - 1)].rstrip("，,；;、 ") + "。"
