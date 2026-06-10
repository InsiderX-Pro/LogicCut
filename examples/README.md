# Examples

This directory contains lightweight release examples. They are intentionally small and do not include generated media, private cookies, API keys, model weights, or copyrighted videos.

## Files

| File | Purpose |
| --- | --- |
| `v03-lite-remix-plan.json` | Example plan for link → comments → 20s comment fast-cut → merge. |
| `theme-opener-plan.example.json` | Example Codex-authored theme opener plan shape. |
| `theme-opener-local-sample-plan.json` | Runnable theme opener plan for the README local sample demo. |
| `public-video-translation-case.json` | 90s public-video translation acceptance case for the built-in local pipeline. |

## How To Use

Copy an example plan into an output directory and adjust the URL or local paths:

```bash
mkdir -p output/demo
cp examples/v03-lite-remix-plan.json output/demo/logiccut_plan.json
logiccut execute --plan output/demo/logiccut_plan.json --dry-run
```

For real processing, replace the example URL with a video you own, are authorized to process, or are legally permitted to transform.

## Local Theme Opener Demo

This path uses a generated local sample video and a prewritten editable plan. It is for installation validation and workflow review, not for judging real semantic clipping quality.

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

The rendered video is written to:

```text
output/theme-opener-sample/project/renders/theme_opener/theme_opener.mp4
```
