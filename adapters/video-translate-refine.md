# video-translate-refine Adapter

LogicCut 的视频翻译主链调用本机 `video-translate-refine` 项目，而不是复用 OmniVoice Studio 的整套视频翻译。

## 目标

当前项目只聚焦视频翻译：

1. 原视频输入；
2. 本地人声分离和 ASR；
3. 本地说话人识别；
4. 大模型翻译；
5. 多种 TTS 后端可切换，本地小机器优先推荐 RGAD Cross-Lingual TTS；
6. 对齐、混音、可选字幕；
7. 输出视频和验收记录。

## 默认链路

LogicCut 调用 `scripts/run_pipeline_profile.py --profile v3`，但会显式覆盖几个关键参数：

| 参数 | LogicCut 默认值 | 说明 |
| --- | --- | --- |
| `--speaker-backend` | `pyannote_local` | 本地 pyannote 说话人识别，不默认调用 Gemini |
| `--asr-text-refine-backend` | `qwen_omni` | ASR 文本修正 |
| `--translate-backend` | `qwen35_plus` | 翻译走本机大模型服务 |
| `--tts-engine` | `rgad-tts` | LogicCut 侧推荐预设，会解析为上游 TTS 参数 |

示例：

```bash
./scripts/logiccut.sh translate-video \
  --input /path/to/input.mp4 \
  --output-dir output/my-run \
  --clip 120 \
  --src-lang en \
  --tgt-lang 中文 \
  --tts-engine rgad-tts \
  --burn-subtitles
```

## TTS 后端

LogicCut 用 `logiccut/tts_engines.py` 将用户可读的 TTS engine 解析成上游参数：

| Engine | 上游模式 | 默认端口 / URL | 说明 |
| --- | --- | --- | --- |
| `rgad-tts` | `legacy_router` | `8393` | 推荐的小机器本地跨语言 TTS。仓库：https://github.com/piedpiperG/rgad-crosslingual-tts，权重：https://huggingface.co/isabeth/rgad-crosslingual-tts |
| `fishaudio` | `legacy_router` | `8321` | 直接使用本机兼容 `/tts` 的 FishAudio S2 服务 |
| `indextts2` | `legacy_router` | `8304` | 使用本机 IndexTTS2 hot-spare gateway |
| `omnivoice` | `legacy_router` | `8391` | 先启动 LogicCut OmniVoice `/tts` adapter，再转发到 OmniVoice API `3900` |
| `fish-speech-s2` | `fish_speech_s2` | `http://127.0.0.1:8392` | 使用上游 Fish Speech adapter server |

OmniVoice 兼容适配器入口：

```bash
./scripts/run_omnivoice_tts_adapter.sh
```

Fish Speech adapter 入口：

```bash
./scripts/run_fish_speech_adapter.sh
```

## 本地 pyannote speaker

默认 `speaker_backend=pyannote_local`。上游会先用现有 ASR 服务获取文本时间轴，再用 `pyannote/speaker-diarization-3.1` 对 vocals 音频做说话人分段，并按时间重叠把 `speaker_id` 写回每条 utterance。

兼容性约束：

- 运行环境使用 `pyannote.audio==3.1.1`、`pyannote.core==5.0.0`、`pyannote.metrics==3.2.1`、`pyannote.pipeline==3.0.1`、`numpy==1.26.4`。
- `PYTHONNOUSERSITE=1` 必须开启，避免 `/root/.local` 中的 `huggingface_hub==1.x` 覆盖 conda env 内的兼容版本。
- HF token 只从用户本机的 `.env.local`、`HF_TOKEN` 或 `HUGGINGFACE_HUB_TOKEN` 读取，不写入 git。

可选约束：

```bash
LOGICCUT_MIN_SPEAKERS=1
LOGICCUT_MAX_SPEAKERS=4
LOGICCUT_SPEAKER_BACKEND=pyannote_local
```

## 字幕

默认会从上游 `timings.json` 导出：

```text
translated_subtitles.srt
```

如果加 `--burn-subtitles`，LogicCut 会再生成：

```text
output_video_subtitled.mp4
```

已有 SRT 可通过 `--subtitle-path /path/to/input.srt` 传入上游，进入 subtitle-direct dubbing。

## 安全边界

LogicCut 不读取、不保存、不提交 API key、HF token 或模型权重。运行日志写入前会做 secret redaction；`output/`、`.env.local` 和媒体文件都被 `.gitignore` 排除。
