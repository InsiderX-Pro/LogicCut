from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logiccut.manifest import load_manifest
from logiccut.media import ensure_sample_video
from logiccut.recipes import SEMANTIC_RECIPE_IDS, init_project, run_recipe


class RecipeSmokeTest(unittest.TestCase):
    def test_semantic_suite_excludes_codex_assisted_theme_opener(self) -> None:
        self.assertNotIn("theme-opener", SEMANTIC_RECIPE_IDS)

    def test_all_recipes_produce_outputs_and_manifest_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            project = root / "project"

            ensure_sample_video(source, duration=3.0)
            init_project(source, project, title="Recipe Demo")
            run_recipe(project, "all", chapters=2)

            manifest = load_manifest(project)
            render_ids = {item["id"] for item in manifest["renders"]}
            clip_ids = {item["id"] for item in manifest["clips"]}
            recipe_ids = {item["id"] for item in manifest["recipes"]}

            self.assertIn("translate_remix", render_ids)
            self.assertIn("highlight_first", render_ids)
            self.assertIn("chapter_01", clip_ids)
            self.assertIn("chapter_02", clip_ids)
            self.assertEqual(
                {"translate-remix", "highlight-first", "chapter-clips"},
                recipe_ids,
            )

            for render in manifest["renders"]:
                path = project / render["path"]
                self.assertTrue(path.exists(), render)
                self.assertGreater(path.stat().st_size, 0, render)

    def test_semantic_highlights_uses_configured_render_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            project = root / "project"
            source.write_bytes(b"placeholder")
            init_project(source, project, title="Semantic Demo")
            plan = {
                "highlights": [
                    {
                        "title": f"Highlight {index}",
                        "start_time": float(index),
                        "end_time": float(index + 1),
                        "score": 90 - index,
                        "hook_sentence": "hook",
                        "virality_reason": "reason",
                    }
                    for index in range(4)
                ]
            }

            def fake_render_clip(_source: Path, output: Path, *_args, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"clip")
                return output

            def fake_concat(inputs: list[Path], output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"".join(path.read_bytes() for path in inputs))
                return output

            with (
                patch.dict("os.environ", {"LOGICCUT_RENDER_HIGHLIGHT_COUNT": "4"}),
                patch("logiccut.recipes._ensure_semantic_plan", return_value=plan),
                patch("logiccut.recipes.render_clip", side_effect=fake_render_clip),
                patch("logiccut.recipes.concat_videos_reencode", side_effect=fake_concat),
            ):
                run_recipe(project, "semantic-highlights")

            manifest = load_manifest(project)
            clips = [item for item in manifest["clips"] if item["recipe"] == "semantic-highlights"]
            timeline = next(item for item in manifest["timeline"] if item["id"] == "semantic_highlights_timeline")
            self.assertEqual(4, len(clips))
            self.assertEqual(4, len(timeline["items"]))

    def test_creator_remix_uses_manifest_video_translation_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            project = root / "project"
            source.write_bytes(b"placeholder")
            init_project(source, project, title="Creator Remix Demo")
            translated = project / "renders" / "video_translation_refine" / "output_video.mp4"
            translated.parent.mkdir(parents=True)
            translated.write_bytes(b"translated")
            plan = {
                "summary": "summary",
                "remix": {"opening_summary": "opening"},
                "highlights": [
                    {
                        "title": "Highlight",
                        "start_time": 0.0,
                        "end_time": 1.0,
                        "score": 0.9,
                        "hook_sentence": "hook",
                        "virality_reason": "reason",
                    }
                ],
                "chapters": [
                    {
                        "title": "Chapter",
                        "summary": "chapter summary",
                        "start_time": 0.0,
                        "end_time": 1.0,
                    }
                ],
            }
            seen_sources: list[Path] = []

            def fake_run_video_translation(project_dir: Path, chapters: int = 4) -> dict:
                manifest = load_manifest(project_dir)
                manifest["renders"].append(
                    {
                        "id": "video_translation",
                        "recipe": "video-translation",
                        "adapter": "video-translate-refine",
                        "path": "renders/video_translation_refine/output_video.mp4",
                    }
                )
                from logiccut.manifest import save_manifest

                save_manifest(project_dir, manifest)
                return manifest

            def fake_render_clip(input_path: Path, output: Path, *_args, **_kwargs) -> Path:
                seen_sources.append(input_path)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"clip")
                return output

            def fake_card(output: Path, *_args, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"card")
                return output

            def fake_concat(inputs: list[Path], output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"".join(path.read_bytes() for path in inputs))
                return output

            with (
                patch("logiccut.recipes.run_video_translation", side_effect=fake_run_video_translation),
                patch("logiccut.recipes.run_semantic_highlights"),
                patch("logiccut.recipes._ensure_semantic_plan", return_value=plan),
                patch("logiccut.recipes.ffprobe_video_size", return_value=(1280, 720)),
                patch("logiccut.recipes.render_text_card", side_effect=fake_card),
                patch("logiccut.recipes.render_clip", side_effect=fake_render_clip),
                patch("logiccut.recipes.concat_videos_reencode", side_effect=fake_concat),
            ):
                run_recipe(project, "creator-remix", chapters=1)

            self.assertIn(translated.resolve(), [path.resolve() for path in seen_sources])

    def test_chapter_card_narration_generates_tts_cards_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            project = root / "project"
            source.write_bytes(b"placeholder")
            init_project(source, project, title="Narrated Cards Demo")
            plan = {
                "highlights": [
                    {
                        "title": "模型能力的真正分水岭",
                        "start_time": 1.0,
                        "end_time": 9.0,
                        "score": 92,
                        "hook_sentence": "这一段解释了 Agent 为什么会变得不一样。",
                        "virality_reason": "语义密度高，观点完整，适合作为章节高光。",
                    },
                    {
                        "title": "工具调用带来的变化",
                        "start_time": 12.0,
                        "end_time": 20.0,
                        "score": 87,
                        "hook_sentence": "这一段给出了产品落地的判断。",
                        "virality_reason": "观点清晰，能承接上一章结论。",
                    },
                ]
            }
            tts_calls: list[dict] = []
            render_calls: list[dict] = []

            def fake_render_html_card_video(**kwargs) -> Path:
                render_calls.append(kwargs)
                kwargs["output_html"].write_text("<html></html>", encoding="utf-8")
                kwargs["output_image"].parent.mkdir(parents=True, exist_ok=True)
                kwargs["output_image"].write_bytes(b"png")
                kwargs["output_video"].parent.mkdir(parents=True, exist_ok=True)
                kwargs["output_video"].write_bytes(b"card")
                return kwargs["output_video"]

            def fake_synthesize(text: str, output_path: Path, **kwargs) -> dict:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"wav")
                tts_calls.append({"text": text, **kwargs})
                return {"success": True, "output_path": str(output_path), "backend": kwargs["engine"]}

            def fake_reference(_source: Path, output_path: Path, **_kwargs) -> Path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"ref")
                return output_path

            def fake_mix(card_video: Path, narration_audio: Path, subtitle_path: Path, output_path: Path, **_kwargs) -> Path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(card_video.read_bytes() + narration_audio.read_bytes() + subtitle_path.read_bytes())
                return output_path

            def fake_concat(inputs: list[Path], output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"".join(path.read_bytes() for path in inputs))
                return output

            with (
                patch.dict(
                    "os.environ",
                    {
                        "LOGICCUT_NARRATION_TTS_ENGINE": "indextts2",
                        "LOGICCUT_NARRATION_VOICE": "logiccut-narrator",
                        "LOGICCUT_CARD_TEMPLATE_SEQUENCE": "news-hook,data-insight",
                    },
                ),
                patch("logiccut.recipes._ensure_semantic_plan", return_value=plan),
                patch("logiccut.recipes.ffprobe_video_size", return_value=(1280, 720)),
                patch("logiccut.recipes.render_html_card_video", side_effect=fake_render_html_card_video),
                patch("logiccut.recipes.prepare_narration_reference", side_effect=fake_reference),
                patch("logiccut.recipes.synthesize_narration_audio", side_effect=fake_synthesize),
                patch("logiccut.recipes.mix_card_with_narration", side_effect=fake_mix),
                patch("logiccut.recipes.concat_videos_reencode", side_effect=fake_concat),
            ):
                run_recipe(project, "chapter-card-narration")

            manifest = load_manifest(project)
            render_ids = {item["id"] for item in manifest["renders"]}
            track_ids = {item["id"] for item in manifest["tracks"]}
            timeline = next(item for item in manifest["timeline"] if item["id"] == "chapter_card_narration_timeline")

            self.assertIn("chapter_card_narration", render_ids)
            self.assertIn("chapter_narration_01", track_ids)
            self.assertIn("chapter_narration_02", track_ids)
            self.assertEqual(2, len(timeline["items"]))
            self.assertEqual("indextts2", tts_calls[0]["engine"])
            self.assertEqual("logiccut-narrator", tts_calls[0]["voice"])
            self.assertEqual("news-hook", render_calls[0]["template_id"])
            self.assertEqual("data-insight", render_calls[1]["template_id"])
            self.assertEqual("news-hook", manifest["clips"][-2]["template_id"])
            self.assertEqual("data-insight", manifest["clips"][-1]["template_id"])

    def test_story_guided_highlights_generates_manifest_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            project = root / "project"
            source.write_bytes(b"placeholder")
            init_project(source, project, title="Story Guided Demo")
            plan = {
                "summary": "剧情出现一个关键冲突。",
                "translated_segments": [{"start": 10.0, "end": 12.0, "text": "你到底想做什么？"}],
                "highlights": [
                    {
                        "id": "h1",
                        "title": "关键对峙",
                        "start_time": 10.0,
                        "end_time": 14.0,
                        "score": 95,
                        "hook_sentence": "What are you doing?",
                        "virality_reason": "角色关系在这里突然紧张。",
                    }
                ],
            }

            def fake_render_story_timeline(project_dir: Path, **_kwargs) -> dict:
                output = project_dir / "renders" / "story_guided_highlights" / "story_guided_highlights.mp4"
                report_json = project_dir / "assets" / "story_guided_highlights" / "story_guided_report.json"
                report_html = project_dir / "assets" / "story_guided_highlights" / "story_guided_report.html"
                clip = project_dir / "clips" / "story_guided_highlights" / "01_narration.mp4"
                subtitle = project_dir / "assets" / "story_guided_highlights" / "01_narration.srt"
                audio = project_dir / "assets" / "story_guided_highlights" / "01_narration.wav"
                for path in (output, report_json, report_html, clip, subtitle, audio):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"ok")
                return {
                    "output": output,
                    "report_json": report_json,
                    "report_html": report_html,
                    "parts": [
                        {
                            "type": "narration",
                            "OST": 0,
                            "path": clip,
                            "raw_clip": clip,
                            "subtitle": subtitle,
                            "start": 6.8,
                            "end": 10.0,
                            "duration": 3.2,
                            "title": "关键对峙",
                            "narration": "剧情从关键对峙开始变味。",
                            "why": "旁白先建立上下文。",
                            "adapter": "fake",
                        }
                    ],
                }

            with (
                patch("logiccut.recipes._ensure_semantic_plan", return_value=plan),
                patch("logiccut.recipes.ffprobe_duration", return_value=30.0),
                patch("logiccut.recipes.render_story_timeline", side_effect=fake_render_story_timeline),
                patch.dict("os.environ", {"LOGICCUT_STORY_STYLE": "story_drama", "LOGICCUT_STORY_ITEM_COUNT": "1"}),
            ):
                run_recipe(project, "story-guided-highlights", chapters=1)

            manifest = load_manifest(project)
            render = next(item for item in manifest["renders"] if item["id"] == "story_guided_highlights")
            timeline = next(item for item in manifest["timeline"] if item["id"] == "story_guided_highlights_timeline")
            recipe_ids = {item["id"] for item in manifest["recipes"]}

            self.assertEqual("story-guided-highlights", render["recipe"])
            self.assertEqual("story_guided_highlights_timeline", render["timeline"])
            self.assertEqual("story_drama", timeline["style_id"])
            self.assertEqual("story-guided-highlights", timeline["recipe"])
            self.assertIn("story-guided-highlights", recipe_ids)

    def test_theme_opener_without_plan_writes_codex_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            project = root / "project"
            source.write_bytes(b"placeholder")
            init_project(source, project, title="Theme Opener Demo")
            transcript = {
                "duration": 60.0,
                "segments": [{"start": 0.0, "end": 5.0, "text": "I feel safe walking here at night."}],
            }

            with (
                patch("logiccut.recipes._ensure_source_transcript", return_value=transcript),
                patch.dict("os.environ", {"LOGICCUT_THEME_OPENER_THEME": "中国安全"}),
            ):
                run_recipe(project, "theme-opener")

            prompt = project / "assets" / "theme_opener" / "codex_prompt.md"
            manifest = load_manifest(project)
            recipe = next(item for item in manifest["recipes"] if item["id"] == "theme-opener")

            self.assertTrue(prompt.exists())
            self.assertEqual("needs_codex_plan", recipe["status"])
            self.assertIn("theme_opener_plan.json", recipe["message"])
            self.assertIn("中国安全", prompt.read_text(encoding="utf-8"))

    def test_theme_opener_with_plan_renders_short_with_subtitles_watermark_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            project = root / "project"
            source.write_bytes(b"placeholder")
            init_project(source, project, title="Theme Opener Demo")
            plan_path = project / "assets" / "theme_opener" / "theme_opener_plan.json"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            (project / "assets" / "source_transcript.json").write_text(
                json.dumps({"segments": []}),
                encoding="utf-8",
            )
            plan_path.write_text(
                json.dumps(
                    {
                        "theme": "中国安全",
                        "opening_hook": "外国人发现中国夜晚很安全。",
                        "clips": [
                            {
                                "start": 1.0,
                                "end": 7.0,
                                "subtitle": "晚上也很安心。",
                                "reason": "直接证明安全感。",
                                "visual_role": "建立主题",
                            },
                            {
                                "start": 10.0,
                                "end": 16.0,
                                "subtitle": "街上还有很多人。",
                                "reason": "补充环境证据。",
                                "visual_role": "增加可信度",
                            },
                            {
                                "start": 20.0,
                                "end": 27.0,
                                "subtitle": "这里让人放松。",
                                "reason": "收束主题。",
                                "visual_role": "情绪收尾",
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            rendered: list[tuple[Path, float, float]] = []
            watermarks: list[str] = []

            def fake_render_clip(input_path: Path, output: Path, start: float, duration: float, **_kwargs) -> Path:
                rendered.append((input_path, start, duration))
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"clip")
                return output

            def fake_burn_subtitles(source_clip: Path, _subtitle: Path, output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(source_clip.read_bytes() + b"+sub")
                return output

            def fake_watermark(source_clip: Path, output: Path, text: str, **_kwargs) -> Path:
                watermarks.append(text)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(source_clip.read_bytes() + b"+wm")
                return output

            def fake_concat(inputs: list[Path], output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"".join(path.read_bytes() for path in inputs))
                return output

            with (
                patch("logiccut.recipes.ffprobe_duration", return_value=80.0),
                patch("logiccut.recipes.render_clip", side_effect=fake_render_clip),
                patch("logiccut.recipes.burn_subtitles", side_effect=fake_burn_subtitles),
                patch("logiccut.recipes.render_text_watermark", side_effect=fake_watermark),
                patch("logiccut.recipes.concat_videos_reencode", side_effect=fake_concat),
            ):
                run_recipe(project, "theme-opener")

            manifest = load_manifest(project)
            render = next(item for item in manifest["renders"] if item["id"] == "theme_opener")
            clips = [item for item in manifest["clips"] if item["recipe"] == "theme-opener"]
            report = project / "assets" / "theme_opener" / "theme_opener_report.html"

            self.assertEqual(3, len(rendered))
            self.assertEqual(["高光剪辑", "高光剪辑", "高光剪辑"], watermarks)
            self.assertEqual("中国安全", render["theme"])
            self.assertEqual(3, len(clips))
            self.assertTrue((project / render["path"]).exists())
            self.assertTrue(report.exists())
            report_html = report.read_text(encoding="utf-8")
            self.assertIn("外国人发现中国夜晚很安全", report_html)
            self.assertIn('src="../../renders/theme_opener/theme_opener.mp4"', report_html)

    def test_guided_highlights_builds_card_then_clip_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            project = root / "project"
            source.write_bytes(b"placeholder")
            init_project(source, project, title="Guided Highlights Demo")
            plan = {
                "highlights": [
                    {
                        "title": "模型能力的真正分水岭",
                        "start_time": 1.0,
                        "end_time": 9.0,
                        "score": 92,
                        "hook_sentence": "这一段解释了 Agent 为什么会变得不一样。",
                        "virality_reason": "语义密度高，观点完整，适合作为章节高光。",
                    },
                    {
                        "title": "工具调用带来的变化",
                        "start_time": 12.0,
                        "end_time": 20.0,
                        "score": 87,
                        "hook_sentence": "这一段给出了产品落地的判断。",
                        "virality_reason": "观点清晰，能承接上一章结论。",
                    },
                ],
                "translated_segments": [
                    {"start": 1.0, "end": 4.0, "text": "第一段字幕"},
                    {"start": 4.0, "end": 9.0, "text": "继续解释模型能力"},
                    {"start": 12.0, "end": 16.0, "text": "第二段字幕"},
                    {"start": 16.0, "end": 20.0, "text": "工具调用改变体验"},
                ],
            }
            rendered_cards: list[dict] = []
            rendered_clips: list[dict] = []
            mixed_cards: list[Path] = []

            def fake_render_html_card_video(**kwargs) -> Path:
                rendered_cards.append(kwargs)
                kwargs["output_html"].parent.mkdir(parents=True, exist_ok=True)
                kwargs["output_html"].write_text("<html></html>", encoding="utf-8")
                kwargs["output_image"].write_bytes(b"png")
                kwargs["output_video"].write_bytes(b"silent-card")
                return kwargs["output_video"]

            def fake_synthesize(_text: str, output_path: Path, **kwargs) -> dict:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"wav")
                return {"success": True, "output_path": str(output_path), "backend": kwargs["engine"]}

            def fake_reference(_source: Path, output_path: Path, **_kwargs) -> Path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"ref")
                return output_path

            def fake_mix(card_video: Path, narration_audio: Path, subtitle_path: Path, output_path: Path, **_kwargs) -> Path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(card_video.read_bytes() + narration_audio.read_bytes() + subtitle_path.read_bytes())
                mixed_cards.append(output_path)
                return output_path

            def fake_render_clip(_source: Path, output: Path, start: float, duration: float, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(f"clip:{start}:{duration}".encode("utf-8"))
                rendered_clips.append({"output": output, "start": start, "duration": duration})
                return output

            def fake_burn_subtitles(source_path: Path, subtitle_path: Path, output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(source_path.read_bytes() + subtitle_path.read_bytes())
                return output

            def fake_concat(inputs: list[Path], output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"".join(path.read_bytes() for path in inputs))
                return output

            with (
                patch.dict(
                    "os.environ",
                    {
                        "LOGICCUT_GUIDED_HIGHLIGHT_COUNT": "2",
                        "LOGICCUT_GUIDED_BURN_SUBTITLES": "1",
                        "LOGICCUT_NARRATION_TTS_ENGINE": "indextts2",
                        "LOGICCUT_CARD_TEMPLATE_SEQUENCE": "news-hook,vertical-hook",
                    },
                ),
                patch("logiccut.recipes._ensure_semantic_plan", return_value=plan),
                patch("logiccut.recipes.ffprobe_video_size", return_value=(1280, 720)),
                patch("logiccut.recipes.render_html_card_video", side_effect=fake_render_html_card_video),
                patch("logiccut.recipes.prepare_narration_reference", side_effect=fake_reference),
                patch("logiccut.recipes.synthesize_narration_audio", side_effect=fake_synthesize),
                patch("logiccut.recipes.mix_card_with_narration", side_effect=fake_mix),
                patch("logiccut.recipes.render_clip", side_effect=fake_render_clip),
                patch("logiccut.recipes.burn_subtitles", side_effect=fake_burn_subtitles),
                patch("logiccut.recipes.concat_videos_reencode", side_effect=fake_concat),
            ):
                run_recipe(project, "guided-highlights", chapters=2)

            manifest = load_manifest(project)
            render = next(item for item in manifest["renders"] if item["id"] == "guided_highlights")
            timeline = next(item for item in manifest["timeline"] if item["id"] == "guided_highlights_timeline")
            clips = {item["id"]: item for item in manifest["clips"]}
            tracks = {item["id"]: item for item in manifest["tracks"]}

            self.assertEqual("renders/guided_highlights/guided_highlights.mp4", render["path"])
            self.assertEqual(4, len(timeline["items"]))
            self.assertEqual(
                ["guided_card_01", "guided_highlight_01", "guided_card_02", "guided_highlight_02"],
                [item["clip_id"] for item in timeline["items"]],
            )
            self.assertEqual("news-hook", clips["guided_card_01"]["template_id"])
            self.assertEqual("vertical-hook", clips["guided_card_02"]["template_id"])
            self.assertEqual("第一段字幕", (project / clips["guided_highlight_01"]["subtitle"]).read_text(encoding="utf-8").splitlines()[2])
            self.assertEqual("语义密度高，观点完整，适合作为章节高光。", clips["guided_highlight_01"]["why_this_clip"])
            self.assertEqual("chapter_card_narration", tracks["guided_narration_01"]["role"])
            self.assertEqual(2, len(rendered_cards))
            self.assertEqual(2, len(rendered_clips))
            self.assertEqual(2, len(mixed_cards))

    def test_personalized_highlights_exports_styles_layouts_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            project = root / "project"
            ref = root / "creator_ref.wav"
            source.write_bytes(b"placeholder")
            ref.write_bytes(b"ref")
            init_project(source, project, title="Personalized Highlights Demo")
            plan = {
                "highlights": [
                    {
                        "title": "模型能力的真正分水岭",
                        "start_time": 1.0,
                        "end_time": 9.0,
                        "score": 92,
                        "hook_sentence": "这一段解释了 Agent 为什么会变得不一样。",
                        "virality_reason": "语义密度高，观点完整，适合作为章节高光。",
                    }
                ],
                "translated_segments": [
                    {"start": 1.0, "end": 4.0, "text": "第一段字幕"},
                    {"start": 4.0, "end": 9.0, "text": "继续解释模型能力"},
                ],
            }
            tts_calls: list[dict] = []
            portrait_calls: list[dict] = []

            def fake_render_html_card_video(**kwargs) -> Path:
                kwargs["output_html"].parent.mkdir(parents=True, exist_ok=True)
                kwargs["output_html"].write_text("<html></html>", encoding="utf-8")
                kwargs["output_image"].write_bytes(b"png")
                kwargs["output_video"].write_bytes(b"silent-card")
                return kwargs["output_video"]

            def fake_synthesize(text: str, output_path: Path, **kwargs) -> dict:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"wav")
                tts_calls.append({"text": text, **kwargs})
                return {"success": True, "output_path": str(output_path), "backend": kwargs["engine"]}

            def fake_mix(card_video: Path, narration_audio: Path, subtitle_path: Path, output_path: Path, **_kwargs) -> Path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(card_video.read_bytes() + narration_audio.read_bytes() + subtitle_path.read_bytes())
                return output_path

            def fake_render_clip(_source: Path, output: Path, start: float, duration: float, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(f"clip:{start}:{duration}".encode("utf-8"))
                return output

            def fake_burn_subtitles(source_path: Path, subtitle_path: Path, output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(source_path.read_bytes() + subtitle_path.read_bytes())
                return output

            def fake_portrait(**kwargs) -> Path:
                portrait_calls.append(kwargs)
                kwargs["output_html"].parent.mkdir(parents=True, exist_ok=True)
                kwargs["output_html"].write_text("<html></html>", encoding="utf-8")
                kwargs["output_image"].write_bytes(b"png")
                kwargs["output_video"].write_bytes(kwargs["source_video"].read_bytes() + b"portrait")
                return kwargs["output_video"]

            def fake_concat(inputs: list[Path], output: Path, **_kwargs) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"".join(path.read_bytes() for path in inputs))
                return output

            with (
                patch.dict(
                    "os.environ",
                    {
                        "LOGICCUT_PERSONALIZED_STYLES": "calm,sharp",
                        "LOGICCUT_PERSONALIZED_LAYOUTS": "landscape,portrait",
                        "LOGICCUT_PERSONALIZED_HIGHLIGHT_COUNT": "1",
                        "LOGICCUT_CREATOR_CATCHPHRASES": "注意看,说人话",
                        "LOGICCUT_CREATOR_REF_WAV": str(ref),
                        "LOGICCUT_NARRATION_TTS_ENGINE": "indextts2",
                    },
                ),
                patch("logiccut.recipes._ensure_semantic_plan", return_value=plan),
                patch("logiccut.recipes.ffprobe_video_size", return_value=(1280, 720)),
                patch("logiccut.recipes.render_html_card_video", side_effect=fake_render_html_card_video),
                patch("logiccut.recipes.prepare_narration_reference") as prepare_ref,
                patch("logiccut.recipes.synthesize_narration_audio", side_effect=fake_synthesize),
                patch("logiccut.recipes.mix_card_with_narration", side_effect=fake_mix),
                patch("logiccut.recipes.render_clip", side_effect=fake_render_clip),
                patch("logiccut.recipes.burn_subtitles", side_effect=fake_burn_subtitles),
                patch("logiccut.recipes.render_portrait_web_video", side_effect=fake_portrait),
                patch("logiccut.recipes.concat_videos_reencode", side_effect=fake_concat),
            ):
                run_recipe(project, "personalized-highlights", chapters=1)

            manifest = load_manifest(project)
            render_ids = {item["id"] for item in manifest["renders"]}
            self.assertIn("personalized_calm_landscape", render_ids)
            self.assertIn("personalized_calm_portrait", render_ids)
            self.assertIn("personalized_sharp_landscape", render_ids)
            self.assertIn("personalized_sharp_portrait", render_ids)
            self.assertIn("personalized_highlights_report", render_ids)
            report_path = project / next(item["path"] for item in manifest["renders"] if item["id"] == "personalized_highlights_report")
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("冷静分析", report)
            self.assertIn("犀利评论", report)
            self.assertIn("注意看", report)
            self.assertIn('src="videos/personalized_calm_landscape.mp4"', report)
            self.assertNotIn("../../renders", report)
            report_json = json.loads((report_path.parent / "personalized_report.json").read_text(encoding="utf-8"))
            self.assertIn(
                "videos/personalized_calm_landscape.mp4",
                {item.get("report_video_path") for item in report_json["renders"]},
            )
            portable_dir = project / "assets" / "personalized_highlights" / "videos"
            self.assertTrue((portable_dir / "personalized_calm_landscape.mp4").exists())
            self.assertTrue((portable_dir / "personalized_sharp_portrait.mp4").exists())
            self.assertEqual(2, len(portrait_calls))
            self.assertFalse(prepare_ref.called)
            self.assertTrue(all(call["backend_options"]["ref_wav"] == str(ref) for call in tts_calls))
            self.assertTrue(any("这段先别温吞" in call["text"] for call in tts_calls))


if __name__ == "__main__":
    unittest.main()
