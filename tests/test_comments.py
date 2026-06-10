from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from logiccut.comments import (
    build_comment_narration_plan,
    build_comment_screenshot_command,
    build_comment_summary_narration,
    build_youtube_comments_command,
    create_comment_freeze_video,
    detect_comment_platform,
    extract_bvid,
    normalize_bilibili_reply,
    normalize_youtube_comment,
    render_comment_freeze_frame,
    scrape_comments,
    sanitize_comment_display_text,
    write_comments_showcase,
    write_comments_report,
)


class CommentsTest(unittest.TestCase):
    def test_build_youtube_comments_command_uses_ytdlp_comment_export(self) -> None:
        cmd = build_youtube_comments_command(
            "https://www.youtube.com/watch?v=abc123",
            max_comments=25,
            cookies=Path("/tmp/cookies.txt"),
        )

        self.assertEqual("yt-dlp", cmd[0])
        self.assertIn("--skip-download", cmd)
        self.assertIn("--write-comments", cmd)
        self.assertIn("--dump-single-json", cmd)
        self.assertIn("--extractor-args", cmd)
        self.assertIn("max_comments=25", " ".join(cmd))
        self.assertIn("--cookies", cmd)
        self.assertEqual("https://www.youtube.com/watch?v=abc123", cmd[-1])

    def test_detect_comment_platform_and_bvid(self) -> None:
        self.assertEqual("youtube", detect_comment_platform("https://youtu.be/abc123"))
        self.assertEqual("bilibili", detect_comment_platform("https://www.bilibili.com/video/BV1gTmCBsExD/"))
        self.assertEqual("BV1gTmCBsExD", extract_bvid("https://www.bilibili.com/video/BV1gTmCBsExD/"))

    def test_sanitize_comment_display_text_removes_unstable_emoji(self) -> None:
        self.assertEqual("看完93阅兵，后台湾网友的真实评论…", sanitize_comment_display_text("看完93閱兵，後台灣網友的真實評論…😏", max_chars=30))

    def test_normalize_youtube_comment_keeps_avatar_and_reply_parent(self) -> None:
        item = normalize_youtube_comment(
            {
                "id": "Ugx1",
                "text": "Great talk",
                "author": "Ada",
                "author_id": "UCada",
                "author_thumbnail": "https://example.com/avatar.jpg",
                "like_count": 12,
                "parent": "root-id",
                "timestamp": 1777476078,
            },
            video_id="abc123",
        )

        self.assertEqual("youtube", item["platform"])
        self.assertEqual("Great talk", item["text"])
        self.assertEqual("https://example.com/avatar.jpg", item["author_avatar"])
        self.assertEqual("root-id", item["parent_id"])
        self.assertEqual(12, item["like_count"])
        self.assertEqual("2026-04-29T15:21:18+00:00", item["published_at"])

    def test_normalize_bilibili_reply_keeps_comment_pictures(self) -> None:
        item = normalize_bilibili_reply(
            {
                "rpid_str": "1001",
                "member": {"uname": "小王", "mid": 88, "avatar": "https://example.com/a.jpg"},
                "content": {
                    "message": "这个角度很适合二创",
                    "pictures": [
                        {"img_src": "https://example.com/p1.jpg", "img_width": 640, "img_height": 360}
                    ],
                },
                "like": 7,
                "rcount": 2,
                "ctime": 1777476078,
            },
            video_id="BVxx",
        )

        self.assertEqual("bilibili", item["platform"])
        self.assertEqual("小王", item["author"])
        self.assertEqual("这个角度很适合二创", item["text"])
        self.assertEqual(1, len(item["images"]))
        self.assertEqual("https://example.com/p1.jpg", item["images"][0]["url"])

    def test_write_comments_report_contains_local_images_and_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            report = write_comments_report(
                output_dir,
                {
                    "platform": "bilibili",
                    "url": "https://www.bilibili.com/video/BVxx/",
                    "video_id": "BVxx",
                    "title": "Demo",
                    "comments": [
                        {
                            "id": "1",
                            "platform": "bilibili",
                            "author": "创作者",
                            "text": "这条评论可以做选题",
                            "like_count": 10,
                            "reply_count": 1,
                            "author_avatar": "",
                            "images": [{"url": "https://example.com/p.jpg", "local_path": "images/p.jpg"}],
                        }
                    ],
                    "images": [{"url": "https://example.com/p.jpg", "local_path": "images/p.jpg"}],
                    "comment_screenshots": [
                        {"path": "comment_screenshots/001.png", "index": 1, "kind": "viewport"}
                    ],
                    "comment_screenshot_manifest": {
                        "status": "login_required",
                        "warning": "Provide cookies to capture deeper comment screenshots.",
                    },
                },
            )

            html = report.read_text(encoding="utf-8")
            self.assertIn("V0.2.2 评论区抓取验收", html)
            self.assertIn("这条评论可以做选题", html)
            self.assertIn("images/p.jpg", html)
            self.assertIn("comment_screenshots/001.png", html)
            self.assertIn("login_required", html)
            self.assertIn("Provide cookies", html)

    def test_build_comment_screenshot_command_uses_playwright_script(self) -> None:
        cmd = build_comment_screenshot_command(
            "https://www.bilibili.com/video/BVxx/",
            Path("/tmp/out"),
            platform="bilibili",
            count=4,
            viewport_width=1080,
            viewport_height=1920,
            cookies=Path("/tmp/bili-cookies.txt"),
        )

        self.assertEqual("node", cmd[0])
        self.assertTrue(any("capture_comment_screenshots.cjs" in item for item in cmd))
        self.assertIn("--url", cmd)
        self.assertIn("https://www.bilibili.com/video/BVxx/", cmd)
        self.assertIn("--output-dir", cmd)
        self.assertIn("--count", cmd)
        self.assertIn("4", cmd)
        self.assertIn("--viewport-width", cmd)
        self.assertIn("1080", cmd)
        self.assertIn("--cookies", cmd)
        self.assertIn("/tmp/bili-cookies.txt", cmd)

    def test_scrape_comments_youtube_writes_json_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            fake = {
                "id": "abc123",
                "title": "Demo",
                "webpage_url": "https://www.youtube.com/watch?v=abc123",
                "comments": [{"id": "c1", "text": "hello", "author": "Ada"}],
            }

            with patch("logiccut.comments.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = json.dumps(fake)
                run.return_value.stderr = ""

                result = scrape_comments(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                    platform="youtube",
                    max_comments=10,
                    download_images=False,
                    capture_screenshots=False,
                )

            self.assertEqual("youtube", result["platform"])
            self.assertEqual(1, result["comment_count"])
            self.assertTrue((output_dir / "comments.json").exists())
            self.assertTrue((output_dir / "comments_report.html").exists())

    def test_scrape_comments_includes_real_comment_screenshots_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            fake = {
                "id": "abc123",
                "title": "Demo",
                "comments": [{"id": "c1", "text": "hello", "author": "Ada"}],
            }
            screenshot_manifest = {
                "status": "ok",
                "screenshots": [
                    {"path": "comment_screenshots/001.png", "index": 1, "kind": "viewport"}
                ],
            }

            with (
                patch("logiccut.comments.subprocess.run") as run,
                patch("logiccut.comments.capture_comment_screenshots", return_value=screenshot_manifest),
            ):
                run.return_value.returncode = 0
                run.return_value.stdout = json.dumps(fake)
                run.return_value.stderr = ""

                result = scrape_comments(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                    platform="youtube",
                    max_comments=10,
                    download_images=False,
                    capture_screenshots=True,
                )

            self.assertEqual(1, result["screenshot_count"])
            self.assertEqual("comment_screenshots/001.png", result["comment_screenshots"][0]["path"])
            saved = json.loads((output_dir / "comments.json").read_text(encoding="utf-8"))
            self.assertEqual(1, saved["screenshot_count"])

    def test_scrape_comments_persists_bound_visual_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            fake = {
                "id": "abc123",
                "title": "Demo",
                "comments": [{"id": "c1", "text": "api text", "author": "Ada"}],
            }
            screenshot_manifest = {
                "status": "ok",
                "screenshots": [],
                "visual_items": [
                    {
                        "id": "youtube_dom_001",
                        "path": "comment_items/001.png",
                        "author": "DOM 作者",
                        "visible_text": "DOM 可见评论文本",
                        "like_count": 12,
                        "reply_count": 2,
                    }
                ],
            }

            with (
                patch("logiccut.comments.subprocess.run") as run,
                patch("logiccut.comments.capture_comment_screenshots", return_value=screenshot_manifest),
            ):
                run.return_value.returncode = 0
                run.return_value.stdout = json.dumps(fake)
                run.return_value.stderr = ""

                result = scrape_comments(
                    "https://www.youtube.com/watch?v=abc123",
                    output_dir,
                    platform="youtube",
                    max_comments=10,
                    download_images=False,
                    capture_screenshots=True,
                )

            self.assertEqual(1, result["visual_item_count"])
            self.assertEqual("DOM 可见评论文本", result["comment_visual_items"][0]["visible_text"])
            saved = json.loads((output_dir / "comments.json").read_text(encoding="utf-8"))
            self.assertEqual("youtube_dom_001", saved["comment_visual_items"][0]["id"])
            self.assertTrue((output_dir / "comment_visual_items.json").exists())
            report_text = (output_dir / "comments_report.html").read_text(encoding="utf-8")
            self.assertIn("完整评论截图", report_text)
            self.assertIn("DOM 可见评论文本", report_text)

    def test_write_comments_showcase_links_screenshot_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            report = write_comments_showcase(
                output_dir,
                [
                    {
                        "platform": "youtube",
                        "title": "Demo",
                        "comment_count": 1,
                        "image_count": 0,
                        "screenshot_count": 1,
                        "comments": [{"author": "Ada", "text": "hello"}],
                        "report_path": "youtube/comments_report.html",
                        "comment_screenshots": [{"path": "youtube/comment_screenshots/001.png"}],
                    }
                ],
            )

            html = report.read_text(encoding="utf-8")
            self.assertIn("真实评论区截图", html)
            self.assertIn("youtube/comment_screenshots/001.png", html)

    def test_create_comment_freeze_video_crops_screenshots_and_writes_manifest(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screenshots = root / "comment_screenshots"
            screenshots.mkdir()
            for index, color in enumerate(["#2441a5", "#6d28d9"], start=1):
                Image.new("RGB", (640, 360), color).save(screenshots / f"{index:03d}.png")
            comments_json = root / "comments.json"
            comments_json.write_text(
                json.dumps(
                    {
                        "platform": "bilibili",
                        "title": "Demo",
                        "comments": [
                            {"author": "A", "text": "第一条评论适合做开头", "like_count": 21, "reply_count": 2},
                            {"author": "B", "text": "第二条评论可以做争议点", "like_count": 8, "reply_count": 1},
                        ],
                        "comment_screenshots": [
                            {"path": "comment_screenshots/001.png", "index": 1},
                            {"path": "comment_screenshots/002.png", "index": 2},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def fake_concat(inputs: list[Path], output: Path, log_file: Path | None = None) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"mp4")
                return output

            with (
                patch("logiccut.comments.run_command") as run_mock,
                patch("logiccut.comments.concat_videos_reencode", side_effect=fake_concat),
            ):
                result = create_comment_freeze_video(
                    comments_json,
                    root / "freeze",
                    layout="landscape",
                    max_frames=2,
                    frame_duration=2.5,
                    size=(960, 540),
                )

            self.assertEqual(2, len(result["frames"]))
            self.assertEqual("landscape", result["layout"])
            self.assertTrue((root / "freeze" / "comment_frames" / "001.png").exists())
            self.assertTrue((root / "freeze" / "comment_freeze_video.mp4").exists())
            self.assertTrue((root / "freeze" / "comment_freeze_manifest.json").exists())
            self.assertTrue((root / "freeze" / "comment_freeze_report.html").exists())
            self.assertEqual((960, 540), Image.open(root / "freeze" / "comment_frames" / "001.png").size)
            self.assertGreaterEqual(run_mock.call_count, 2)

    def test_create_comment_freeze_video_prefers_bound_visual_items(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item_dir = root / "comment_items"
            item_dir.mkdir()
            Image.new("RGB", (600, 240), "#19d37a").save(item_dir / "001.png")
            comments_json = root / "comments.json"
            comments_json.write_text(
                json.dumps(
                    {
                        "platform": "bilibili",
                        "title": "Demo",
                        "comments": [{"author": "API 作者", "text": "API 评论不应该参与这张图"}],
                        "comment_visual_items": [
                            {
                                "id": "bilibili_dom_001",
                                "path": "comment_items/001.png",
                                "author": "DOM 作者",
                                "visible_text": "这是一条完整 DOM 评论",
                                "like_count": 77,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def fake_concat(inputs: list[Path], output: Path, log_file: Path | None = None) -> Path:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"mp4")
                return output

            with (
                patch("logiccut.comments.run_command"),
                patch("logiccut.comments.concat_videos_reencode", side_effect=fake_concat),
            ):
                result = create_comment_freeze_video(
                    comments_json,
                    root / "freeze",
                    layout="landscape",
                    max_frames=1,
                    frame_duration=2.0,
                    size=(960, 540),
                )

            self.assertEqual("bilibili_dom_001", result["frames"][0]["visual_item_id"])
            self.assertEqual("这是一条完整 DOM 评论", result["frames"][0]["text"])
            self.assertEqual("comment_items/001.png", result["frames"][0]["source_visual_item"])

    def test_render_comment_freeze_frame_makes_screenshot_the_dominant_visual(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screenshot = root / "shot.png"
            output = root / "frame.png"
            Image.new("RGB", (640, 360), "#18d36e").save(screenshot)

            render_comment_freeze_frame(
                screenshot,
                output,
                comment={"author": "A", "text": "这条评论不应该被画成右侧解说卡", "like_count": 12},
                title="Demo",
                platform="bilibili",
                index=1,
                total=1,
                layout="landscape",
                size=(960, 540),
            )

            image = Image.open(output).convert("RGB")
            green_pixels = 0
            pixels = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
            for r, g, b in pixels:
                if g > 150 and r < 80 and b < 140:
                    green_pixels += 1
            self.assertGreater(green_pixels / (960 * 540), 0.60)

    def test_render_comment_freeze_frame_preserves_full_wide_comment_item(self) -> None:
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screenshot = root / "wide-comment.png"
            output = root / "frame.png"
            source = Image.new("RGB", (760, 116), "#f8fafc")
            draw = ImageDraw.Draw(source)
            draw.rectangle((0, 0, 11, 115), fill="#ff0000")
            draw.rectangle((748, 0, 759, 115), fill="#ff0000")
            draw.rectangle((80, 36, 680, 78), fill="#18d36e")
            source.save(screenshot)

            render_comment_freeze_frame(
                screenshot,
                output,
                comment={"author": "A", "text": "这张评论截图必须完整显示", "like_count": 12},
                title="Demo",
                platform="visual_item",
                index=1,
                total=1,
                layout="landscape",
                size=(960, 540),
            )

            image = Image.open(output).convert("RGB")
            red_pixels = 0
            pixels = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
            for r, g, b in pixels:
                if r > 200 and g < 80 and b < 80:
                    red_pixels += 1
            self.assertGreater(red_pixels, 500)

    def test_build_comment_narration_plan_pairs_comments_with_frames(self) -> None:
        comments_data = {
            "platform": "bilibili",
            "title": "Demo",
            "comments": [
                {"author": "A", "text": "这条评论说明争议点", "like_count": 21, "reply_count": 2},
                {"author": "B", "text": "这条评论适合做收尾", "like_count": 8, "reply_count": 1},
            ],
        }
        freeze_manifest = {
            "frames": [
                {"path": "comment_frames/001.png", "source_screenshot": "comment_screenshots/001.png"},
                {"path": "comment_frames/002.png", "source_screenshot": "comment_screenshots/002.png"},
            ]
        }

        plan = build_comment_narration_plan(comments_data, freeze_manifest, max_items=2)

        self.assertEqual("logiccut.comment_narration.v1", plan["schema_version"])
        self.assertEqual(2, len(plan["items"]))
        self.assertEqual("comment_frames/001.png", plan["items"][0]["frame"])
        self.assertNotIn("来自", plan["items"][0]["narration"])
        self.assertIn("评论区", plan["items"][0]["narration"])
        self.assertIn("争议点", plan["items"][0]["why"])

    def test_build_comment_narration_plan_summarizes_visible_text_without_author_attribution(self) -> None:
        comments_data = {
            "platform": "bilibili",
            "title": "Demo",
            "comment_visual_items": [
                {
                    "id": "bilibili_dom_001",
                    "path": "comment_items/001.png",
                    "author": "评论作者",
                    "visible_text": "大家都在说这件事最大的看点是反差和争议，不只是单纯吐槽。",
                    "like_count": 321,
                    "reply_count": 9,
                }
            ],
        }
        freeze_manifest = {
            "frames": [
                {
                    "path": "comment_frames/001.png",
                    "visual_item_id": "bilibili_dom_001",
                    "text": "大家都在说这件事最大的看点是反差和争议，不只是单纯吐槽。",
                }
            ]
        }

        plan = build_comment_narration_plan(comments_data, freeze_manifest, max_items=1)

        narration = plan["items"][0]["narration"]
        self.assertNotIn("来自", narration)
        self.assertNotIn("他说", narration)
        self.assertIn("评论区", narration)
        self.assertIn("反差", narration)
        self.assertEqual("bilibili_dom_001", plan["items"][0]["visual_item_id"])

    def test_build_comment_summary_narration_extracts_specific_bilibili_topics(self) -> None:
        text = "如果放弃联合国和安理会的职务，退出五常之后，所有约束是不是都不存在了？"

        narration = build_comment_summary_narration(text, {"like_count": 0}, index=0)

        self.assertIn("五常", narration)
        self.assertIn("国际规则", narration)
        self.assertNotIn("情绪、观点和讨论点", narration)

    def test_build_comment_narration_plan_uses_video_centered_story_voice(self) -> None:
        comments_data = {
            "platform": "bilibili",
            "title": "看完93阅兵，后台湾网友的真实评论",
            "comment_visual_items": [
                {
                    "id": "v1",
                    "path": "comment_items/001.png",
                    "visible_text": "如果退出五常，联合国的约束是不是就不存在了？",
                },
                {
                    "id": "v2",
                    "path": "comment_items/002.png",
                    "visible_text": "我们的军事真的很强吗？科技真的领先吗？",
                },
                {
                    "id": "v3",
                    "path": "comment_items/003.png",
                    "visible_text": "退出五常就要打仗吗？战争没啥意义吧。",
                },
            ],
        }
        freeze_manifest = {
            "frames": [
                {"path": "comment_frames/001.png", "visual_item_id": "v1"},
                {"path": "comment_frames/002.png", "visual_item_id": "v2"},
                {"path": "comment_frames/003.png", "visual_item_id": "v3"},
            ]
        }

        plan = build_comment_narration_plan(comments_data, freeze_manifest, max_items=3)
        narrations = [item["narration"] for item in plan["items"]]

        self.assertIn("这条视频", narrations[0])
        self.assertIn("有的人说", narrations[0])
        self.assertIn("有的人说", narrations[1])
        self.assertIn("有的人说", narrations[2])
        self.assertIn("串起来看", narrations[-1])
        self.assertNotIn("……如果", "\n".join(narrations))
        self.assertNotIn("来自", "\n".join(narrations))

    def test_build_comment_narration_plan_cleans_youtube_dom_text_and_summarizes_in_chinese(self) -> None:
        comments_data = {
            "platform": "youtube",
            "title": "Andrej Karpathy: From Vibe Coding to Agentic Engineering",
            "comment_visual_items": [
                {
                    "id": "youtube_dom_001",
                    "path": "comment_items/001.png",
                    "author": "@isiTsotsi",
                    "visible_text": "@isiTsotsi 1个月前 Great 1.5 hour talk from Andrej Karpathy 424 回复 4 条回复",
                    "like_count": 424,
                },
                {
                    "id": "youtube_dom_002",
                    "path": "comment_items/002.png",
                    "author": "@Arcticwhir",
                    "visible_text": "@Arcticwhir 1个月前 that was a nice quote in the end \"You can outsource your thinking but you can't outsource your understanding\" 203 回复",
                    "like_count": 203,
                },
            ],
        }
        freeze_manifest = {
            "frames": [
                {"path": "comment_frames/001.png", "visual_item_id": "youtube_dom_001"},
                {"path": "comment_frames/002.png", "visual_item_id": "youtube_dom_002"},
            ]
        }

        plan = build_comment_narration_plan(comments_data, freeze_manifest, max_items=2)
        joined = "\n".join(item["narration"] for item in plan["items"])

        self.assertIn("长谈", joined)
        self.assertIn("思考可以外包", joined)
        self.assertNotIn("@isiTsotsi", joined)
        self.assertNotIn("1个月前", joined)
        self.assertNotIn("Great 1.5 hour", joined)
        self.assertNotIn("补上AI", joined)
        self.assertNotIn("拉回AI", joined)


if __name__ == "__main__":
    unittest.main()
