# LogicCut

> **Don’t just translate videos. Repurpose them.**

LogicCut is an open-source **AI Video Repurposing Agent** for creator workflows. Give it a local video or an authorized video link, and it helps turn the source into translated videos, theme-based highlight openers, comment-recap clips, and composed creator-ready shorts.

LogicCut 不是「又一个视频翻译工具」，也不是「又一个下载器」。它的目标是把创作者真实工作流串起来：导入视频、理解内容、找到爆点主题、剪出高光开头、翻译/字幕/配音、分析评论区，再合并成可以继续发布和二创的视频素材。

<p align="center">
  <img alt="Status" src="https://img.shields.io/badge/status-public_preview-334155">
  <img alt="Version" src="https://img.shields.io/badge/version-v0.3-0f766e">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10+-3776ab">
  <img alt="FFmpeg" src="https://img.shields.io/badge/ffmpeg-required-2563eb">
  <img alt="Agent Friendly" src="https://img.shields.io/badge/agent--friendly-CLI-111827">
  <img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-blue">
</p>

<p align="center">
  <img alt="LogicCut demo collage: one source video to theme opener, comment recap, localized subtitles, and final remix" src="docs/assets/demo/logiccut-demo-hero.jpg" width="88%">
</p>

<p align="center">
  <img alt="LogicCut theme opener demo GIF" src="docs/assets/demo/theme-opener-demo.gif" width="66%">
</p>

## Demo Gallery

| Scenario | Preview | What LogicCut Produces |
| --- | --- | --- |
| Theme opener | <img src="docs/assets/demo/theme_opener.jpg" width="260" alt="Theme opener preview"> | A 15-30s creator hook around one angle, with subtitles and an editable cut plan. |
| Comment recap | <img src="docs/assets/demo/comment_item.jpg" width="260" alt="Comment recap preview"> | Public comments become fast visual material for recap or reaction videos. |
| Localized draft | <img src="docs/assets/demo/translation.jpg" width="260" alt="Localized subtitle preview"> | A translated/subtitled video draft, with optional dubbing when TTS is configured. |
| Visual templates | <img src="docs/assets/demo/templates.jpg" width="260" alt="Template system preview"> | HTML/card-style creator overlays for intros, chapters, and explanations. |

LogicCut currently supports four creator outputs: **theme openers**, **localized video drafts**, **public-comment recap clips**, and **final remix composition**.

## Why LogicCut

Most open-source video tools solve one stage: download, subtitle, translate, or cut. LogicCut focuses on the creator workflow around **video repurposing**:

1. Import a local video or authorized link.
2. Understand the source content.
3. Pick a creator-oriented theme.
4. Cut and subtitle the best moments.
5. Turn public comments into additional video material.
6. Merge multiple parts into one output.

The long-term story is simple: **teach the agent a video repurposing logic once, then apply it to many new videos.**

## Core Features

| Feature | Status | Notes |
| --- | --- | --- |
| Local video input | Ready | Recommended path for first-time users. |
| Video merge | Ready | `logiccut merge` normalizes video/audio streams with FFmpeg. |
| CLI planning workflow | Ready | `capabilities`, `guide`, `doctor`, `sample`, `plan`, `execute`, `merge`. |
| YouTube / Bilibili link import | Beta | Powered by `yt-dlp`; use only for authorized or legally permitted content. |
| Public comment import / analysis | Beta | Public comments, screenshots, single-comment visual items. |
| Comment-to-video | Beta | Freeze-frame clips and optional narration workflow. |
| Theme opener | Beta | Agent-assisted theme selection and 15-30s opener rendering. |
| Video translation | Beta | Adapter-based; full quality depends on configured ASR/TTS backends. |
| Multi-backend TTS | Experimental | FishAudio / IndexTTS2 / OmniVoice style adapters. |
| One-command `create` workflow | Experimental | Convenience wrapper around `plan` + `execute`; inspect the generated plan for real projects. |
| Editing recipe learning | Roadmap | Reuse a learned editing logic across different source videos. |
| Optional Web UI | Roadmap | Timeline review and easier creator-facing interaction. |

## Current Limitations

LogicCut is currently in public preview. The recommended first-time path is local video input, comment fast-cut, and video merge.

Some workflows depend on external services or platform availability:

- Link import may require cookies or fail when platforms change their access rules.
- Video translation quality depends on the configured ASR, translation, and TTS backends.
- Theme opener generation is still improving for long videos and complex narratives.
- Comment-to-video currently focuses on simple freeze-frame and narration workflows.
- There is no full Web UI yet; the project is currently CLI-first and agent-friendly.

If a workflow fails, please open an issue with the command, logs, source type, and expected output.

## Quick Start

### 1. Install

Linux / macOS:

```bash
git clone https://github.com/piedpiperG/LogicCut.git
cd LogicCut

./scripts/install.sh --profile lite
source .venv/bin/activate
logiccut doctor --profile lite --json
```

Windows PowerShell:

```powershell
git clone https://github.com/piedpiperG/LogicCut.git
cd LogicCut

powershell -ExecutionPolicy Bypass -File scripts/install.ps1 -Profile lite
.venv\Scripts\Activate.ps1
python -m logiccut.cli doctor --profile lite --json
```

### 2. Path A: Smoke Test

```bash
logiccut capabilities
logiccut guide --task remix
logiccut sample --output output/sample/a.mp4 --duration 1
logiccut sample --output output/sample/b.mp4 --duration 1
logiccut merge \
  --inputs output/sample/a.mp4 output/sample/b.mp4 \
  --output output/sample/final_remix.mp4
```

This path does not depend on a platform link, cookies, API keys, or model services.

It only verifies installation, FFmpeg, audio/video stream handling, and CLI wiring. It is not the core repurposing demo.

### 3. Path B: Local Repurposing Demo

This path renders a tiny theme opener from a generated local video and a reviewable edit plan. The fallback transcript is synthetic and exists only so first-time users can test the repurposing workflow without downloading third-party ASR models.

```bash
logiccut sample --output output/theme-opener-sample/source.mp4 --duration 35

logiccut init \
  --input output/theme-opener-sample/source.mp4 \
  --project-dir output/theme-opener-sample/project \
  --title "Local Theme Opener Demo"

LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1 \
logiccut run --project-dir output/theme-opener-sample/project --recipe theme-opener
```

The first run writes a review prompt:

```text
output/theme-opener-sample/project/assets/theme_opener/codex_prompt.md
```

To render the local demo, copy the included editable plan and run the recipe again:

```bash
cp examples/theme-opener-local-sample-plan.json \
  output/theme-opener-sample/project/assets/theme_opener/theme_opener_plan.json

LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1 \
logiccut run --project-dir output/theme-opener-sample/project --recipe theme-opener
```

Output:

```text
output/theme-opener-sample/project/renders/theme_opener/theme_opener.mp4
output/theme-opener-sample/project/assets/theme_opener/theme_opener_report.html
```

For real videos, use real ASR instead of `LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1`.

### 4. Path C: Authorized Video Link

Generate a reviewable plan first:

```bash
logiccut plan \
  --url "https://www.youtube.com/watch?v=96jN2OCOfLs" \
  --project-dir output/my-case \
  --tasks download,comments,comment-freeze,merge \
  --target-lang 中文 \
  --theme auto \
  --comment-duration 20
```

Dry-run before doing network or media work:

```bash
logiccut execute --plan output/my-case/logiccut_plan.json --dry-run
```

Then execute:

```bash
logiccut execute --plan output/my-case/logiccut_plan.json
```

### 5. Path D: Merge Existing Clips

```bash
logiccut merge \
  --inputs opener.mp4 translated.mp4 comments.mp4 \
  --output output/my-case/final/final_remix.mp4
```

## Agent-Friendly Workflow

LogicCut provides a CLI-native workflow that can be used manually or controlled by coding agents such as Codex, Claude Code, or other agentic development tools. An agent should read [AGENTS.md](AGENTS.md), then follow this order:

1. `logiccut capabilities`
2. `logiccut doctor --profile lite --json`
3. `logiccut guide --task remix`
4. `logiccut plan ...`
5. Review and edit `logiccut_plan.json` if needed.
6. `logiccut execute --plan ...`
7. `logiccut merge ...`
8. Verify final video streams with `ffprobe`.

See [docs/codex-quickstart.md](docs/codex-quickstart.md) for the detailed workflow.

## Recipes

Release examples are stored in [examples/](examples/) and [recipes/](recipes/):

- `recipes/remix-lite.json`: link → comments → comment fast-cut → merge.
- `recipes/theme-opener.json`: local video → Codex theme opener.
- `recipes/comment-fast-cut.json`: comments JSON → 20s fast comment recap.
- `examples/v03-lite-remix-plan.json`: an example `logiccut_plan.json`.

## Architecture

```mermaid
flowchart LR
    Source[Video URL or local video] --> Import[Download / Local Import]
    Import --> Plan[Reviewable edit plan]
    Plan --> Translate[Video Translation]
    Plan --> Opener[Theme Opener]
    Plan --> Comments[Comment-to-Video]
    Translate --> Merge[Merge]
    Opener --> Merge
    Comments --> Merge
    Merge --> Final[Creator-ready remix]
```

## Comparison

| Project Type | Typical Focus | LogicCut Position |
| --- | --- | --- |
| VideoLingo / pyVideoTrans | Translation, subtitles, dubbing | LogicCut can call translation backends, but focuses on repurposing workflow. |
| yt-dlp | Downloading media | LogicCut uses link import as one input method, not as the product story. |
| MoneyPrinterTurbo | Generate new short videos from prompts | LogicCut repurposes existing videos into new creator outputs. |
| OpusClip-style tools | Auto short clipping | LogicCut emphasizes reasoning cuts, comments, and composable recipes. |

## Responsible Use

LogicCut is designed for videos you own, are authorized to process, or are legally permitted to transform. Link import and public comment analysis are provided for creator workflows, research, backup, and accessibility scenarios. You are responsible for complying with platform terms, copyright law, privacy requirements, and local regulations.

Do not commit or publish:

- `.env.local`
- API keys
- cookies
- Hugging Face tokens
- model weights
- generated videos containing private or copyrighted material

When using comment screenshots in public videos, consider blurring usernames, avatars, and other personal information.

## Installation Profiles

| Profile | Use Case | Command |
| --- | --- | --- |
| `lite` | Download, comments, screenshots, merge | `./scripts/install.sh --profile lite` |
| `creator` | `lite` + extra creator tooling | `./scripts/install.sh --profile creator` |
| `full` | Translation and local model services | `./scripts/install.sh --profile full` |

Full profile depends on external model services and is best tested on Linux or WSL2 with GPU support.

## Known Working Environment

The current release candidate has been validated on:

| Item | Version / Notes |
| --- | --- |
| OS | Ubuntu-style Linux environment; WSL2 recommended for Windows GPU work. |
| Python | 3.10+ |
| FFmpeg / FFprobe | Required for every media workflow. |
| Browser automation | Playwright is used for real comment-section screenshots. |
| Lite profile | Download, comments, screenshot capture, sample generation, merge, local theme-opener demo. |
| Full profile | Translation and TTS adapters require additional model services and are best treated as deployment-specific. |

## Development

```bash
python3 -m pytest -q
bash -n scripts/install.sh scripts/logiccut.sh scripts/env.sh
python3 -m py_compile scripts/bootstrap.py logiccut/*.py
```

Expected release-candidate validation:

```text
136 passed
```

## Roadmap

- Better theme proposal UI and multi-theme selection.
- Stronger subtitle style presets.
- Privacy-safe comment rendering with optional blur.
- More reliable long-video semantic highlight selection.
- Learnable editing recipes that transfer a creator’s style to new videos.
- Optional Web UI and timeline review.

## Support

If LogicCut is useful for your workflow, a GitHub star helps others discover the project. Real examples, recipes, bug reports, and failure cases are especially welcome.
