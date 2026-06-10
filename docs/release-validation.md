# Release Validation

Validation date: 2026-06-10

This file records the current `LogicCut-Releash` public-preview validation.

## Directory Scope

Included:

- `logiccut/`
- `scripts/`
- `configs/`
- `tests/`
- `docs/`
- `examples/`
- `recipes/`
- `docs/assets/demo/`
- `AGENTS.md`
- `INSTALL.md`
- `README.md`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `.github/workflows/tests.yml`

Excluded:

- `.env.local`
- API keys
- cookies
- model weights
- `.venv/`
- `third_party/`
- `output/`
- `logs/`
- `model_cache/`

## Validation Commands

```bash
python3 -m pytest -q
# 136 passed
```

```bash
bash -n scripts/install.sh scripts/logiccut.sh scripts/env.sh scripts/smoke_pyannote.sh scripts/run_fish_speech_adapter.sh
# exit 0
```

```bash
python3 -m py_compile scripts/bootstrap.py logiccut/*.py
# exit 0
```

```bash
test -f docs/assets/demo/logiccut-demo-hero.jpg
test -f docs/assets/demo/theme-opener-demo.gif
test -f .github/workflows/tests.yml
# exit 0
```

Demo asset sizes:

```text
docs/assets/demo/logiccut-demo-hero.jpg 168K
docs/assets/demo/theme-opener-demo.gif 929K
docs/assets/demo total 1.4M
```

```bash
test -f docs/assets/demo/README.md
test -f examples/theme-opener-local-sample-plan.json
# exit 0
```

```bash
./scripts/install.sh --profile lite
# installed lite profile into .venv
```

```bash
./scripts/logiccut.sh doctor --profile lite --json
# summary: {'ok': True, 'missing': [], 'failed': []}
```

```bash
./scripts/logiccut.sh plan \
  --url "https://www.youtube.com/watch?v=96jN2OCOfLs" \
  --project-dir output/v03-release-plan \
  --tasks download,comments,comment-freeze,merge \
  --target-lang 中文 \
  --theme auto \
  --comment-duration 20

./scripts/logiccut.sh execute \
  --plan output/v03-release-plan/logiccut_plan.json \
  --dry-run
# generated 4 steps: download, comments, comment-freeze, merge
```

```bash
./scripts/logiccut.sh sample --output output/v03-release-smoke/a.mp4 --duration 1
./scripts/logiccut.sh sample --output output/v03-release-smoke/b.mp4 --duration 1
./scripts/logiccut.sh merge \
  --inputs output/v03-release-smoke/a.mp4 output/v03-release-smoke/b.mp4 \
  --output output/v03-release-smoke/final/final_remix.mp4

ffprobe -v error \
  -show_entries format=duration \
  -show_entries stream=codec_type,width,height \
  -of default=nw=1 \
  output/v03-release-smoke/final/final_remix.mp4
```

Result:

```text
codec_type=video
width=1280
height=720
codec_type=audio
duration=2.049000
```

```bash
python3 -m logiccut.cli sample \
  --output output/theme-opener-sample/source.mp4 \
  --duration 35

python3 -m logiccut.cli init \
  --input output/theme-opener-sample/source.mp4 \
  --project-dir output/theme-opener-sample/project \
  --title "Local Theme Opener Demo"

LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1 \
python3 -m logiccut.cli run \
  --project-dir output/theme-opener-sample/project \
  --recipe theme-opener

cp examples/theme-opener-local-sample-plan.json \
  output/theme-opener-sample/project/assets/theme_opener/theme_opener_plan.json

LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1 \
python3 -m logiccut.cli run \
  --project-dir output/theme-opener-sample/project \
  --recipe theme-opener

ffprobe -v error \
  -show_entries format=duration \
  -show_entries stream=codec_type,width,height \
  -of default=nw=1 \
  output/theme-opener-sample/project/renders/theme_opener/theme_opener.mp4
```

Result:

```text
codec_type=video
width=1280
height=720
codec_type=audio
duration=22.657000
```

The first `theme-opener` run produced `assets/theme_opener/codex_prompt.md`; the second run rendered `renders/theme_opener/theme_opener.mp4` from the included reviewable plan. `LOGICCUT_ALLOW_TRANSCRIPT_FALLBACK=1` was used only to avoid third-party ASR downloads for the local demo.

## Security Scan

The release directory was scanned for:

- local machine paths
- Hugging Face token patterns
- private infrastructure paths
- large media files
- model/cache/runtime directories

No release-blocking files were found outside ignored runtime directories.

The only remaining `hf_` matches are Hugging Face API function names such as `hf_hub_download`, not tokens.
