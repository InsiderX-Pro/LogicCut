from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoryStyle:
    id: str
    label: str
    opening: str
    narration_pattern: str
    original_reason_pattern: str
    voice: str


STORY_STYLES: dict[str, StoryStyle] = {
    "story_news": StoryStyle(
        id="story_news",
        label="新闻解说",
        opening="用新闻感的节奏，把这段素材讲成一条清晰的故事线。",
        narration_pattern="先看{title}。这里的关键不是热闹，而是{reason}",
        original_reason_pattern="保留原声，因为这一刻能直接证明前面的判断。",
        voice="logiccut-news-narrator",
    ),
    "story_travel": StoryStyle(
        id="story_travel",
        label="旅行探店",
        opening="用探店博主的方式，先抛出最想看的体验，再让画面自己说话。",
        narration_pattern="这一站先看{title}。真正抓人的点是{reason}",
        original_reason_pattern="这里保留原声和现场反应，因为食物、环境和语气比解释更有冲击力。",
        voice="logiccut-travel-narrator",
    ),
    "story_drama": StoryStyle(
        id="story_drama",
        label="剧情解说",
        opening="用短剧解说的节奏，抓住冲突、反转和人物关系。",
        narration_pattern="这一幕是{title}。它要放在这里，是因为{reason}",
        original_reason_pattern="这里保留原声，因为台词和表演是情绪爆点。",
        voice="logiccut-drama-narrator",
    ),
    "story_roast": StoryStyle(
        id="story_roast",
        label="犀利吐槽",
        opening="用更尖锐的口吻，把普通片段改成有观点的二创。",
        narration_pattern="先别急着划走，{title}这段有问题。它好看在{reason}",
        original_reason_pattern="保留原声，让观众直接听到这个反差点。",
        voice="logiccut-roast-narrator",
    ),
}


def get_story_style(style_id: str | None) -> StoryStyle:
    key = str(style_id or "story_news").strip() or "story_news"
    return STORY_STYLES.get(key, STORY_STYLES["story_news"])
