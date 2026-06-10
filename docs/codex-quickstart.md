# Codex Quickstart

这份文档是给用户和 Codex 一起看的。用户只需要描述目标，Codex 根据这里的命令完成安装、计划、执行和验证。

## 1. 发现能力

```bash
logiccut capabilities
```

重点看：

- `download`
- `translate-video`
- `setup translation`
- `theme-opener`
- `comments`
- `comment-freeze`
- `comment-narration`
- `merge`

## 2. 检查环境

```bash
logiccut doctor --profile lite --json
```

如果要跑完整翻译：

```bash
logiccut doctor --profile full --json
```

## 3. 读取任务向导

```bash
logiccut guide --task download
logiccut guide --task translate
logiccut guide --task highlight
logiccut guide --task comments
logiccut guide --task remix
```

## 4. 本地视频翻译

先检查翻译依赖计划：

```bash
logiccut setup translation --profile asr --dry-run
```

真实视频需要 ASR。Codex 可以执行 `logiccut setup translation --profile asr --install`，或使用用户提供的 `--transcript-json`。

第一次运行生成 transcript 和 Codex prompt：

```bash
logiccut translate-video \
  --backend logiccut-local \
  --input output/my-case/source.mp4 \
  --output-dir output/my-case/translation \
  --clip 90 \
  --tgt-lang 中文
```

然后读取：

```text
output/my-case/translation/codex_translation_prompt.md
```

写入：

```text
output/my-case/translation/translated_segments.json
```

再次运行渲染：

```bash
logiccut translate-video \
  --backend logiccut-local \
  --input output/my-case/source.mp4 \
  --output-dir output/my-case/translation \
  --translation-json output/my-case/translation/translated_segments.json \
  --clip 90 \
  --tgt-lang 中文
```

公开视频验收 case 见：

```text
examples/public-video-translation-case.json
```

## 5. 本地二创开头 Demo

这条路径不依赖视频平台、cookies、API key 或第三方 ASR 权重，用于验证 LogicCut 的「可审查计划 → 渲染二创开头」流程。

```bash
logiccut sample --output output/theme-opener-sample/source.mp4 --duration 35
logiccut init \
  --input output/theme-opener-sample/source.mp4 \
  --project-dir output/theme-opener-sample/project \
  --title "Local Theme Opener Demo"

LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1 \
logiccut run --project-dir output/theme-opener-sample/project --recipe theme-opener
```

第一次运行会生成：

```text
output/theme-opener-sample/project/assets/theme_opener/codex_prompt.md
```

Codex 可以读取这个 prompt，也可以先复制仓库内示例计划完成安装验收：

```bash
cp examples/theme-opener-local-sample-plan.json \
  output/theme-opener-sample/project/assets/theme_opener/theme_opener_plan.json

LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1 \
logiccut run --project-dir output/theme-opener-sample/project --recipe theme-opener
```

真实视频不要使用 fallback transcript，应配置真实 ASR 或第三方 transcriber。

## 6. 从视频链接生成二创计划

```bash
logiccut plan \
  --url "https://www.youtube.com/watch?v=96jN2OCOfLs" \
  --project-dir output/v03-demo \
  --tasks download,comments,comment-freeze,merge \
  --target-lang 中文 \
  --theme auto \
  --comment-duration 20
```

生成：

```text
output/v03-demo/logiccut_plan.json
```

Codex 应该先审查这个 JSON，再执行。

## 7. 执行计划

先 dry-run：

```bash
logiccut execute --plan output/v03-demo/logiccut_plan.json --dry-run
```

确认后执行：

```bash
logiccut execute --plan output/v03-demo/logiccut_plan.json
```

## 8. 合并多段视频

```bash
logiccut merge \
  --inputs output/v03-demo/comments/fast-cut-20s/comment_freeze_video.mp4 another_segment.mp4 \
  --output output/v03-demo/final/final_remix.mp4
```

## 9. 验证输出

```bash
ffprobe -v error \
  -show_entries format=duration \
  -show_entries stream=codec_type,width,height \
  -of default=nw=1 \
  output/v03-demo/final/final_remix.mp4
```

检查点：

- 有视频流。
- 有音频流。
- 时长符合用户要求。
- 字幕没有明显遮挡。
- 评论截图没有半截评论。
- HTML 报告能打开。

## Codex 决策原则

- 不要直接提交 `.env.local`、cookies、token、模型权重或生成视频。
- 遇到需要大模型判断的高光选段时，Codex 自己阅读 transcript 和 prompt 后写 plan。
- 视频翻译优先使用 `--backend logiccut-local`，Codex 自己阅读 prompt 并写 `translated_segments.json`。
- 如果需要配音，再切换到外部 `video-translate-refine` 或 TTS 服务；本地小机器优先推荐 `--tts-engine rgad-tts`，对应仓库是 https://github.com/piedpiperG/rgad-crosslingual-tts。
- 不要提交 RGAD / ASR / pyannote 等模型权重。Codex 只记录 GitHub、Hugging Face 来源和本机路径。
- 如果评论截图被平台限制，说明需要 cookies，而不是假装已抓全。
