import unittest
from tools.ffmpeg_tool import FFmpegTool

class TestFFmpegTool(unittest.TestCase):
    def test_ffmpeg_availability(self):
        ff = FFmpegTool()
        available, info = ff.check_availability()
        self.assertTrue(available)
        self.assertIn("ffmpeg", info.lower())

if __name__ == "__main__":
    unittest.main()
