# Release Checklist

Use this checklist before publishing a public LogicCut release repository.

## Repository

- [ ] New public Git repository URL is confirmed.
- [ ] `README.md` clone URL points to the final public repository.
- [ ] `README.md` first screen has the AI video repurposing story.
- [ ] `README.md` has a visible Demo Gallery.
- [ ] Demo assets are lightweight and stored under `docs/assets/demo/`.
- [ ] The first runnable demo proves more than sample generation and merge.
- [ ] `LICENSE` is present.
- [ ] `THIRD_PARTY_NOTICES.md` is present.
- [ ] `AGENTS.md` is present for Codex users.
- [ ] `INSTALL.md` has Linux / macOS / Windows instructions.
- [ ] `examples/` and `recipes/` contain lightweight text-only examples.
- [ ] GitHub Actions test workflow is present.

## Security

- [ ] No `.env.local`.
- [ ] No API keys.
- [ ] No cookies.
- [ ] No Hugging Face tokens.
- [ ] No model weights.
- [ ] No generated media files.
- [ ] No local machine paths such as `/workspace/...`.

## Validation

- [ ] `python3 -m pytest -q`
- [ ] `bash -n scripts/install.sh scripts/logiccut.sh scripts/env.sh`
- [ ] `python3 -m py_compile scripts/bootstrap.py logiccut/*.py`
- [ ] `test -f docs/assets/demo/logiccut-demo-hero.jpg`
- [ ] `test -f docs/assets/demo/theme-opener-demo.gif`
- [ ] `test -f docs/assets/demo/README.md`
- [ ] `test -f examples/theme-opener-local-sample-plan.json`
- [ ] `test -f examples/public-video-translation-case.json`
- [ ] `logiccut capabilities`
- [ ] `logiccut guide --task remix`
- [ ] `logiccut guide --task translate`
- [ ] `logiccut setup translation --profile minimal --dry-run`
- [ ] `logiccut doctor --profile lite --json`
- [ ] `logiccut plan ...`
- [ ] `logiccut execute --dry-run ...`
- [ ] `logiccut merge ...`
- [ ] Local theme opener demo renders `output/theme-opener-sample/project/renders/theme_opener/theme_opener.mp4`
- [ ] Local translation smoke renders `output/translation-smoke/translation/output_video_subtitled.mp4`

## Release Notes

Recommended public label:

```text
v0.3-public-preview
```

Recommended message:

```text
LogicCut is an open-source AI video repurposing agent. It turns one video link or local video into translated videos, theme-based highlight openers, comment-recap clips, and composed creator-ready shorts.
```
