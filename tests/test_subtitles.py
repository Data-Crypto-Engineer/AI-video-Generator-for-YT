import os
import tempfile
import unittest
from models.scene import Scene
from services.subtitle_service import SubtitleService, format_timestamp

class TestSubtitles(unittest.TestCase):
    def test_format_timestamp(self):
        self.assertEqual(format_timestamp(0.0), "00:00:00,000")
        self.assertEqual(format_timestamp(65.45), "00:01:05,450")
        self.assertEqual(format_timestamp(3661.125), "01:01:01,125")

    def test_generate_srt(self):
        scenes = [
            Scene(
                id=1,
                narration="Deep beneath the ocean waves lies an unknown ecosystem.",
                visual_prompt="Deep ocean glowing creatures",
                duration=5.0
            ),
            Scene(
                id=2,
                narration="Here, darkness reigns, but bioluminescent lights reveal ancient life.",
                visual_prompt="Bioluminescent jellyfish in black water",
                duration=6.0
            )
        ]

        with tempfile.NamedTemporaryFile("w", suffix=".srt", delete=False) as f:
            tmp_srt = f.name

        try:
            service = SubtitleService()
            out_path = service.generate_srt(scenes, tmp_srt)
            self.assertTrue(os.path.exists(out_path))
            with open(out_path, "r", encoding="utf-8") as rf:
                content = rf.read()

            self.assertIn("-->", content)
            self.assertIn("Deep beneath", content)
            self.assertIn("bioluminescent", content)
        finally:
            if os.path.exists(tmp_srt):
                os.remove(tmp_srt)

if __name__ == "__main__":
    unittest.main()
