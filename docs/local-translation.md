# Local Translation Pipeline

LogicCut now includes a minimal local video translation pipeline under `logiccut/translation/`.

The goal is not to ship model weights in this repository. The goal is to give Codex a clear file-based workflow so it can run on a user machine without requiring the user to configure a separate LLM API key.

## What This Pipeline Does

`logiccut translate-video --backend logiccut-local` does four things:

1. Get a timed transcript from a local video.
2. Write `codex_translation_prompt.md`.
3. Wait for Codex to write `translated_segments.json`.
4. Render `translated_subtitles.srt` and `output_video_subtitled.mp4`.

The first run usually stops with:

```json
{
  "status": "needs_codex_translation"
}
```

Codex should then read the prompt and write:

```text
output/my-case/translation/translated_segments.json
```

After the second run, LogicCut burns the translated subtitles into the video.

## Commands

Prepare:

```bash
logiccut setup translation --profile asr --dry-run
```

For a real video, install ASR dependencies on the user's machine:

```bash
logiccut setup translation --profile asr --install
```

If the user already has a transcript, skip ASR and pass `--transcript-json`.

Generate transcript and prompt:

```bash
logiccut translate-video \
  --backend logiccut-local \
  --input output/my-case/source.mp4 \
  --output-dir output/my-case/translation \
  --clip 90 \
  --tgt-lang 中文
```

After Codex writes `translated_segments.json`:

```bash
logiccut translate-video \
  --backend logiccut-local \
  --input output/my-case/source.mp4 \
  --output-dir output/my-case/translation \
  --translation-json output/my-case/translation/translated_segments.json \
  --clip 90 \
  --tgt-lang 中文
```

Output:

```text
output/my-case/translation/output_video_subtitled.mp4
output/my-case/translation/translated_subtitles.srt
output/my-case/translation/translation_report.html
output/my-case/translation/translation_manifest.json
```

## Model And Project Sources

LogicCut does not include these repositories or weights. Users should download them on their own machine when they need the corresponding capability.

| Capability | Recommended Source | Notes |
| --- | --- | --- |
| Local ASR | https://github.com/SYSTRAN/faster-whisper | Used for real transcript generation when installed. |
| Faster Whisper base | https://huggingface.co/Systran/faster-whisper-base | Small ASR model for smoke tests. |
| Faster Whisper large-v3 | https://huggingface.co/Systran/faster-whisper-large-v3 | Higher-quality ASR model for production. |
| Speaker diarization | https://huggingface.co/pyannote/speaker-diarization-3.1 | Optional; requires Hugging Face access approval and `HF_TOKEN`. |
| pyannote segmentation | https://huggingface.co/pyannote/segmentation-3.0 | Dependency for pyannote diarization. |
| pyannote embedding | https://huggingface.co/pyannote/wespeaker-voxceleb-resnet34-LM | Dependency for pyannote diarization. |
| Fish Speech TTS | https://github.com/fishaudio/fish-speech | Optional dubbing backend. |
| IndexTTS2 | https://github.com/index-tts/index-tts and https://huggingface.co/IndexTeam/IndexTTS-2 | Optional Chinese-focused TTS backend. |
| OmniVoice | https://github.com/k2-fsa/OmniVoice and https://huggingface.co/k2-fsa/OmniVoice | Optional multilingual TTS backend. |
| OmniVoice Studio | https://github.com/debpalash/OmniVoice-Studio | Optional studio-style TTS and dubbing reference. |

## Translation Driver

The local pipeline uses a file contract instead of a runtime LLM API:

```text
source_transcript.json
  -> codex_translation_prompt.md
  -> translated_segments.json
  -> translated_subtitles.srt
  -> output_video_subtitled.mp4
```

This is the key Codex-driven behavior: Codex reads the prompt and writes the translation file directly.

## Optional Dubbing

The minimal built-in pipeline currently produces a translated subtitled video. Dubbing is still routed through optional services:

- `--backend video-translate-refine` for the existing full dubbing adapter.
- Fish Speech / IndexTTS2 / OmniVoice service adapters when the user has installed them locally.

Do not commit downloaded weights, `.env.local`, cookies, generated videos, or token files.
