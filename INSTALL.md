# LogicCut V0.3 安装指南

LogicCut V0.3 面向「用户通过 Codex 调用」的使用方式。推荐默认执行标准安装，把创作者工作流需要的基础能力一次装好；不要把 `lite` 当作正常用户入口。模型和重型 TTS 服务按用户任务再由 Codex 推荐、说明原因，并按需安装。

## 安装档位

| Profile | 适合场景 | 包含能力 |
| --- | --- | --- |
| `standard` | 默认用户安装 | Python 依赖、`yt-dlp`、Playwright、OpenCC、下载、评论抓取、评论快切、合并、二创基础工具 |
| `full` | Linux / WSL2 重模型安装 | 在 Codex 给出任务级模型选择后，安装第三方仓库、ASR、pyannote、TTS 适配 |
| `lite` | 调试烟测 | 只用于排查极小安装问题，不推荐普通用户使用 |

Windows 原生建议先使用 `standard`。完整 GPU 翻译、pyannote 和 TTS 服务更推荐 Linux 或 WSL2。

## Codex 推荐顺序

Codex 应先执行标准安装，再根据用户任务推荐模型：

| 用户任务 | 推荐选择 | 说明 |
| --- | --- | --- |
| 外语视频翻译到中文，要求本地轻量 | `rgad-tts` + `logiccut setup translation --profile asr` | 默认推荐路径，适合小机器和跨语言中文配音。 |
| 多语言配音 | `omnivoice` | 用户明确要多语言时再安装 OmniVoice / OmniVoice Studio。 |
| 中文音质优先 | `indextts2` | 用户更在意中文发音、参考音色或情绪时使用。 |
| 已有 FishAudio / Fish Speech S2 服务 | `fishaudio` / `fish-speech-s2` | 复用用户已有服务或走 Fish Speech 原生 adapter。 |
| 多说话人视频 | `pyannote/speaker-diarization-3.1` | 需要 HF 授权和 `HF_TOKEN`，只在任务需要时安装。 |

## 系统依赖

所有平台都需要：

- Python 3.10+
- Git
- FFmpeg 和 FFprobe
- Node.js 18+（评论截图和 HTML 渲染需要）

可选：

- `uv`：完整环境安装推荐使用。
- NVIDIA GPU + CUDA：视频翻译、ASR 和 TTS 加速推荐。
- Hugging Face Token：pyannote gated 模型需要。

## Linux / macOS

```bash
git clone https://github.com/piedpiperG/LogicCut.git
cd LogicCut

./scripts/install.sh
source .venv/bin/activate
logiccut doctor --profile standard --json
```

如果 Codex 判断当前任务需要完整环境：

```bash
./scripts/install.sh --profile full
logiccut doctor --profile full --json
```

翻译模块可以单独检查：

```bash
logiccut setup translation --profile asr --dry-run
```

`minimal` 只覆盖已有 transcript 的 Codex 文件翻译链；`asr` 会提示或安装 faster-whisper；`full` 会提示 pyannote 和可选 TTS 后端。模型和权重不包含在仓库里，来源见 [docs/local-translation.md](docs/local-translation.md)。

## Windows PowerShell

```powershell
git clone https://github.com/piedpiperG/LogicCut.git
cd LogicCut

powershell -ExecutionPolicy Bypass -File scripts/install.ps1
.venv\Scripts\Activate.ps1
python -m logiccut.cli doctor --profile standard --json
```

完整翻译链路建议在 WSL2 中执行 Linux 安装命令。

## 本地配置

复制示例配置：

```bash
cp .env.local.example .env.local
```

按需填写：

```bash
HF_TOKEN=...
BILIBILI_COOKIES=/path/to/bilibili-cookies.txt
LOGICCUT_VIDEO_TRANSLATION_BACKEND=video-translate-refine
LOGICCUT_TTS_ENGINE=rgad-tts
LOGICCUT_TTS_PORTS=8393
```

`.env.local` 已被 `.gitignore` 排除，不要提交真实密钥和 cookies。

本地小机器优先推荐 [RGAD Cross-Lingual TTS](https://github.com/piedpiperG/rgad-crosslingual-tts)。它适合「外语 prompt audio 克隆音色 → 中文文本配音」的翻译场景，权重见 [Hugging Face](https://huggingface.co/isabeth/rgad-crosslingual-tts)。LogicCut 只保存仓库和权重来源，不把模型权重放进本仓库。

## 验证安装

```bash
logiccut capabilities
logiccut guide --task remix
logiccut doctor --profile standard --json
```

轻量视频合并验收：

```bash
logiccut sample --output output/v03-smoke/a.mp4 --duration 1
logiccut sample --output output/v03-smoke/b.mp4 --duration 1
logiccut merge \
  --inputs output/v03-smoke/a.mp4 output/v03-smoke/b.mp4 \
  --output output/v03-smoke/final.mp4
```

本地二创开头验收：

```bash
logiccut sample --output output/theme-opener-sample/source.mp4 --duration 35
logiccut init \
  --input output/theme-opener-sample/source.mp4 \
  --project-dir output/theme-opener-sample/project \
  --title "Local Theme Opener Demo"

LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1 \
logiccut run --project-dir output/theme-opener-sample/project --recipe theme-opener

cp examples/theme-opener-local-sample-plan.json \
  output/theme-opener-sample/project/assets/theme_opener/theme_opener_plan.json

LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1 \
logiccut run --project-dir output/theme-opener-sample/project --recipe theme-opener
```

`LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1` 只用于本地演示，真实视频应配置 ASR。

本地视频翻译验收：

```bash
logiccut translate-video \
  --backend logiccut-local \
  --input output/theme-opener-sample/source.mp4 \
  --output-dir output/translation-smoke \
  --clip 60 \
  --tgt-lang 中文 \
  --allow-fallback-transcript
```

第一次运行会生成 `codex_translation_prompt.md` 和 `translated_segments.todo.json`。Codex 按 prompt 写入 `translated_segments.json` 后，再运行：

```bash
logiccut translate-video \
  --backend logiccut-local \
  --input output/theme-opener-sample/source.mp4 \
  --output-dir output/translation-smoke \
  --translation-json output/translation-smoke/translated_segments.json \
  --clip 60 \
  --tgt-lang 中文 \
  --allow-fallback-transcript
```

## 常见问题

### `ffmpeg` 找不到

确认 `ffmpeg` 和 `ffprobe` 都在 PATH 上。Linux 可以使用包管理器安装，macOS 可使用 Homebrew，Windows 可安装 FFmpeg release 并配置 PATH。

### Bilibili 评论截图只能截到少量评论

这是平台登录门槛。导出浏览器 cookies，并在 `logiccut comments` 中传 `--cookies /path/to/cookies.txt`。

### `full` profile 装不上

先确认标准安装是否通过：`./scripts/install.sh && logiccut doctor --profile standard --json`。完整翻译链路涉及第三方仓库、模型和 GPU 环境，建议在 Linux / WSL2 中配置；Codex 应先说明为什么需要 `full`，再执行安装。
