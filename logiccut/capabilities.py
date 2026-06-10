from __future__ import annotations

from copy import deepcopy
from typing import Any


_FEATURES: list[dict[str, Any]] = [
    {
        "id": "download",
        "version": "0.1",
        "title": "Video download",
        "description": "Download YouTube / Bilibili videos with yt-dlp and save metadata.",
        "commands": ["logiccut download"],
        "inputs": ["youtube_url", "bilibili_url"],
        "outputs": ["downloaded_video", "download.json"],
    },
    {
        "id": "translate-video",
        "version": "0.1",
        "title": "Video translation",
        "description": "Translate and dub a local video through the video-translate-refine backend.",
        "commands": ["logiccut translate-video"],
        "inputs": ["local_video"],
        "outputs": ["translated_video", "manifest.json", "optional_subtitled_video"],
    },
    {
        "id": "semantic-highlights",
        "version": "0.1",
        "title": "Semantic highlight clipping",
        "description": "Cut high-value clips from transcripts or semantic plans.",
        "commands": ["logiccut run --recipe semantic-highlights"],
        "inputs": ["local_video", "project_dir"],
        "outputs": ["highlight_clips", "highlight_report"],
    },
    {
        "id": "theme-opener",
        "version": "0.2",
        "title": "Codex-assisted theme opener",
        "description": "Let Codex select a theme and render a 15-30 second opener with subtitles and reasons.",
        "commands": ["logiccut run --recipe theme-opener"],
        "inputs": ["local_video", "theme"],
        "outputs": ["theme_opener.mp4", "theme_opener_report.html"],
    },
    {
        "id": "comments",
        "version": "0.2.2",
        "title": "Comment crawling",
        "description": "Fetch YouTube / Bilibili comments, screenshots, and single-comment visual items.",
        "commands": ["logiccut comments"],
        "inputs": ["youtube_url", "bilibili_url", "optional_cookies"],
        "outputs": ["comments.json", "comment_screenshots", "comment_items", "comments_report.html"],
    },
    {
        "id": "comment-freeze",
        "version": "0.2.2",
        "title": "Comment fast-cut video",
        "description": "Turn comment screenshots into a short freeze-frame video.",
        "commands": ["logiccut comment-freeze"],
        "inputs": ["comments.json"],
        "outputs": ["comment_freeze_video.mp4", "comment_freeze_manifest.json"],
    },
    {
        "id": "comment-narration",
        "version": "0.2.2",
        "title": "Comment narration video",
        "description": "Generate a comment-story narration plan, TTS voiceover, subtitles, and final video.",
        "commands": ["logiccut comment-narration"],
        "inputs": ["comments.json", "comment_freeze_manifest.json", "tts_service"],
        "outputs": ["comment_narration_video.mp4", "comment_narration_plan.json"],
    },
    {
        "id": "merge",
        "version": "0.3",
        "title": "Video merge",
        "description": "Merge translated, highlight, and comment videos into one creator-ready video.",
        "commands": ["logiccut merge"],
        "inputs": ["video_segments"],
        "outputs": ["final_remix.mp4", "merge_manifest.json"],
    },
]


_GUIDES: dict[str, dict[str, Any]] = {
    "download": {
        "task": "download",
        "title": "下载 YouTube / Bilibili 视频",
        "steps": [
            {
                "title": "准备输出目录",
                "commands": ["mkdir -p output/my-case/download"],
            },
            {
                "title": "下载视频并保存 metadata",
                "commands": [
                    'logiccut download --url "<video-url>" --output-dir output/my-case/download --prefix source'
                ],
            },
        ],
        "notes": ["Bilibili 高清素材或更多字幕可能需要 cookies。"],
    },
    "translate": {
        "task": "translate",
        "title": "把本地视频翻译成目标语言",
        "steps": [
            {
                "title": "确认视频已经在本地",
                "commands": ["logiccut download --url \"<video-url>\" --output-dir output/my-case/download --prefix source"],
            },
            {
                "title": "调用 video-translate-refine 后端",
                "commands": [
                    "logiccut translate-video --input output/my-case/download/source.mp4 --output-dir output/my-case/translation --tgt-lang 中文 --burn-subtitles"
                ],
            },
        ],
        "notes": ["视频翻译依赖本地 ASR、pyannote 和 TTS 服务，先运行 logiccut doctor。"],
    },
    "highlight": {
        "task": "highlight",
        "title": "生成主题高光开头",
        "steps": [
            {
                "title": "初始化项目",
                "commands": [
                    "logiccut init --input output/my-case/download/source.mp4 --project-dir output/my-case/project --title \"My Case\""
                ],
            },
            {
                "title": "让 Codex 写主题计划",
                "commands": [
                    "LOGICCUT_THEME_OPENER_THEME=安全感 logiccut run --project-dir output/my-case/project --recipe theme-opener"
                ],
            },
            {
                "title": "渲染主题开头",
                "commands": ["logiccut run --project-dir output/my-case/project --recipe theme-opener"],
            },
        ],
        "notes": ["Codex 需要先阅读 assets/theme_opener/codex_prompt.md，再写 theme_opener_plan.json。"],
    },
    "comments": {
        "task": "comments",
        "title": "抓评论并做评论视频",
        "steps": [
            {
                "title": "抓评论和真实截图",
                "commands": [
                    "logiccut comments --url \"<video-url>\" --output-dir output/my-case/comments --limit 30 --screenshot-count 8"
                ],
            },
            {
                "title": "做 20 秒评论快切",
                "commands": [
                    "logiccut comment-freeze --comments-json output/my-case/comments/comments.json --output-dir output/my-case/comments/fast-cut-20s --max-frames 8 --frame-duration 2.5"
                ],
            },
            {
                "title": "可选：做评论解说视频",
                "commands": [
                    "logiccut comment-narration --comments-json output/my-case/comments/comments.json --freeze-manifest output/my-case/comments/fast-cut-20s/comment_freeze_manifest.json --output-dir output/my-case/comments/narration --tts-engine indextts2 --ref-wav /path/to/ref.wav"
                ],
            },
        ],
        "notes": ["Bilibili 要截取更多评论时建议传 cookies。"],
    },
    "merge": {
        "task": "merge",
        "title": "合并多个视频片段",
        "steps": [
            {
                "title": "按希望的顺序传入片段",
                "commands": [
                    "logiccut merge --inputs opener.mp4 translated.mp4 comments.mp4 --output output/my-case/final/final_remix.mp4"
                ],
            }
        ],
        "notes": ["merge 会重编码并统一分辨率、帧率和音频格式。"],
    },
    "remix": {
        "task": "remix",
        "title": "从链接到二创视频",
        "steps": [
            {
                "title": "生成可审查计划",
                "commands": [
                    "logiccut plan --url \"<video-url>\" --project-dir output/my-case --tasks download,comments,comment-freeze,merge --target-lang 中文 --theme auto"
                ],
            },
            {
                "title": "让 Codex 审查计划",
                "commands": ["cat output/my-case/logiccut_plan.json"],
            },
            {
                "title": "执行计划",
                "commands": ["logiccut execute --plan output/my-case/logiccut_plan.json"],
            },
            {
                "title": "合并最终视频",
                "commands": [
                    "logiccut merge --inputs output/my-case/comments/fast-cut-20s/comment_freeze_video.mp4 output/my-case/translation/final.mp4 --output output/my-case/final/final_remix.mp4"
                ],
            },
        ],
        "notes": ["Codex 应该根据用户目标调整 theme、时长、片段顺序和是否加入评论解说。"],
    },
}


def build_capabilities() -> dict[str, Any]:
    return {
        "name": "LogicCut",
        "version": "0.3",
        "usage_modes": ["codex", "cli", "local-first"],
        "features": deepcopy(_FEATURES),
        "recommended_flow": ["doctor", "plan", "execute", "merge"],
    }


def build_guide(task: str) -> dict[str, Any]:
    key = task.strip().lower()
    if key not in _GUIDES:
        supported = ", ".join(sorted(_GUIDES))
        raise ValueError(f"unknown guide task: {task}; supported: {supported}")
    return deepcopy(_GUIDES[key])


def supported_guide_tasks() -> list[str]:
    return sorted(_GUIDES)
