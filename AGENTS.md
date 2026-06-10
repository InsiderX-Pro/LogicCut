# LogicCut Codex 操作协议

LogicCut V0.3 的目标是让用户在 Codex 里完成视频二创工作流。你作为 Codex 代理时，应该先发现能力、检查环境，再生成计划并执行。

## 默认工作顺序

1. 运行 `logiccut capabilities`，确认当前项目支持哪些能力。
2. 运行 `logiccut doctor --profile lite --json`，检查本机基础环境。
3. 根据用户目标运行 `logiccut guide --task <task>`，读取任务步骤。
4. 对完整二创任务，先运行 `logiccut plan` 生成 `logiccut_plan.json`。
5. 审查 plan，必要时修改主题、时长、顺序、TTS 参数或 cookies。
6. 运行 `logiccut execute --plan <path>` 或分步运行 CLI。
7. 用 `logiccut merge` 合并高光、翻译、评论等多段视频。
8. 验证输出视频时长、分辨率、音频流和 HTML 报告。

## 常用任务

### 下载视频

```bash
logiccut download \
  --url "<youtube-or-bilibili-url>" \
  --output-dir output/my-case/download \
  --prefix source
```

### 视频翻译

```bash
logiccut translate-video \
  --input output/my-case/download/source.mp4 \
  --output-dir output/my-case/translation \
  --tgt-lang 中文 \
  --burn-subtitles
```

完整翻译依赖 `video-translate-refine`、本地 ASR、pyannote 和 TTS 服务。轻量验收时可以先用 `--dry-run` 检查命令。

### 主题高光开头

```bash
logiccut init \
  --input output/my-case/download/source.mp4 \
  --project-dir output/my-case/project \
  --title "My Case"

LOGICCUT_THEME_OPENER_THEME=安全感 \
logiccut run --project-dir output/my-case/project --recipe theme-opener
```

第一次运行可能只生成 `assets/theme_opener/codex_prompt.md`。你需要读取 prompt，并写入 `theme_opener_plan.json` 后再运行第二次。

### 评论区视频

```bash
logiccut comments \
  --url "<youtube-or-bilibili-url>" \
  --output-dir output/my-case/comments \
  --limit 30 \
  --screenshot-count 8

logiccut comment-freeze \
  --comments-json output/my-case/comments/comments.json \
  --output-dir output/my-case/comments/fast-cut-20s \
  --max-frames 8 \
  --frame-duration 2.5
```

Bilibili 如果需要更多真实评论区截图，传 `--cookies /path/to/cookies.txt`。

### 合并视频

```bash
logiccut merge \
  --inputs opener.mp4 translated.mp4 comments.mp4 \
  --output output/my-case/final/final_remix.mp4
```

`merge` 会重编码并统一视频尺寸、帧率和音频格式。

### 一次生成计划并执行

```bash
logiccut plan \
  --url "<video-url>" \
  --project-dir output/my-case \
  --tasks download,comments,comment-freeze,merge \
  --target-lang 中文 \
  --theme auto

logiccut execute --plan output/my-case/logiccut_plan.json
```

或者：

```bash
logiccut create \
  --url "<video-url>" \
  --project-dir output/my-case \
  --tasks download,comments,comment-freeze,merge
```

## 不要提交的内容

不要提交以下内容：

- `.env.local`
- cookies
- API Key
- Hugging Face Token
- 模型权重
- `output/`、`logs/`、`model_cache/`
- 生成的 `.mp4`、`.wav`、`.mp3`

如果需要提供样例，使用 README 中的本地路径说明，或放在发布资产中。
