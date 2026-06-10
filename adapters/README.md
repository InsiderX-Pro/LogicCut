# Adapter Plan

LogicCut通过 adapter 复用外部开源项目。第一阶段不直接合并外部项目源码，只做：

1. clone 固定版本；
2. 检查依赖；
3. 定义输入输出产物；
4. 后续通过 CLI/API/subprocess 接入。

## Video Translation Adapter

Primary upstream: `debpalash/OmniVoice-Studio`

Expected input:

- source video path
- target language
- voice / dubbing options
- output directory

Expected output:

- translated subtitle
- dubbed audio
- translated video
- speaker/voice metadata when upstream provides it

Integration status:

- Clone and doctor first.
- Do not store model credentials in this repo.
- Check upstream license before copying code or redistributing packaged builds.

## Highlight Clipping Adapter

Primary upstream: `SamurAIGPT/AI-Youtube-Shorts-Generator`

Expected input:

- source or translated video path
- transcript/subtitle if already available
- desired clip duration
- output aspect ratio

Expected output:

- scored highlight clips
- vertical shorts
- clip metadata
- selected hook clip

Integration status:

- Clone and doctor first.
- Use as subprocess adapter after upstream setup is understood.
- Keep generated clips under project `output/`.

## Rough Cut Adapter

Primary upstream: `WyattBlue/auto-editor`

Expected input:

- source video path
- silence/threshold settings

Expected output:

- rough cut video
- edit decision metadata when available

Integration status:

- Can be installed into the reusable `.venv`.
- Used before highlight clipping to remove low-value dead air.

## Timeline UI Reference

Primary upstream: `Augani/openreel-video`

This is a UI and architecture reference for browser-based timeline editing. It is not the MVP render engine. The MVP should only implement a lightweight review timeline for:

- selecting the opening hook;
- ordering clips;
- previewing subtitles;
- exporting through FFmpeg.
