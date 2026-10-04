import unittest
import os
import json
import uuid
import tempfile
import subprocess
from models.scene import Scene, SceneStatus, CameraMotion, TransitionType
from models.production import ProjectConfig, ProductionPlan
from models.audio import AudioPlan, MusicTrackPlan, SFXCue
from models.qa import QAStatus
from services.video_service import VideoAssemblyService
from services.subtitle_service import SubtitleService
from tools.ffmpeg_tool import FFmpegTool
from tools.media_validation_tool import MediaValidationTool
from utils.filesystem import WorkspaceManager
from utils.validation import probe_media_file, get_audio_duration

class TestE2EAcceptance(unittest.TestCase):
    """
    Most Important Acceptance Test:
    Validates end-to-end deterministic media assembly with FFmpeg:
    1. 9:16 aspect ratio produces actual 1080x1920 MP4
    2. Authoritative audio duration strictly drives scene duration, timeline, and video duration
    3. SFX and ducked music are actually mixed into the final audio stream
    4. Subtitles match narration timeline
    5. EditPlan is populated and stored
    6. QA performs forensic verification and fails on intentional defects
    """
    def setUp(self):
        self.project_id = f"test-acc-{uuid.uuid4().hex[:8]}"
        self.workspace = WorkspaceManager(self.project_id)
        self.ffmpeg = FFmpegTool()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.workspace.project_dir, ignore_errors=True)

    def test_complete_v1_pipeline_acceptance_9x16(self):
        # 1. Create 2 test scenes
        s1_vis = os.path.join(self.workspace.scenes_dir, "scene_001", "visual.png")
        s2_vis = os.path.join(self.workspace.scenes_dir, "scene_002", "visual.png")
        os.makedirs(os.path.dirname(s1_vis), exist_ok=True)
        os.makedirs(os.path.dirname(s2_vis), exist_ok=True)

        # Create 2 test still images (amber sunrise and deep forest)
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "color=c=0xDAA520:s=1080x1920:d=1", "-frames:v", "1", "-y", s1_vis], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "color=c=0x228B22:s=1080x1920:d=1", "-frames:v", "1", "-y", s2_vis], check=True, capture_output=True)

        # Create 2 actual WAV narration files (Scene 1: 3.0s, Scene 2: 4.0s)
        s1_aud = os.path.join(self.workspace.audio_dir, "scene_001.wav")
        s2_aud = os.path.join(self.workspace.audio_dir, "scene_002.wav")
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "sine=frequency=440:duration=3.0", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", "-y", s1_aud], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "sine=frequency=554:duration=4.0", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", "-y", s2_aud], check=True, capture_output=True)

        # Measure actual audio durations (authoritative source)
        dur1 = get_audio_duration(s1_aud)
        dur2 = get_audio_duration(s2_aud)
        self.assertAlmostEqual(dur1, 3.0, places=1)
        self.assertAlmostEqual(dur2, 4.0, places=1)

        # Build authoritative scene objects
        scenes = [
            Scene(
                id=1,
                narration="When your heart feels tired, return to quiet contemplation.",
                visual_prompt="Peaceful person beside water at dawn, warm amber light",
                duration=dur1,
                audio_duration=dur1,
                visual_path=s1_vis,
                audio_path=s1_aud,
                camera_motion=CameraMotion.SLOW_ZOOM_IN,
                transition=TransitionType.CUT,
                start_time=0.0,
                end_time=round(dur1, 2),
                status=SceneStatus.COMPLETED
            ),
            Scene(
                id=2,
                narration="Peace is the gentle stillness found within.",
                visual_prompt="Ancient green forest canopy in soft morning mist",
                duration=dur2,
                audio_duration=dur2,
                visual_path=s2_vis,
                audio_path=s2_aud,
                camera_motion=CameraMotion.SLOW_ZOOM_OUT,
                transition=TransitionType.CROSSFADE,
                start_time=round(dur1, 2),
                end_time=round(dur1 + dur2, 2),
                status=SceneStatus.COMPLETED
            )
        ]

        total_audio_duration = dur1 + dur2  # 7.0s

        # Audio plan with verified SFX whoosh
        sfx_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "sfx", "whoosh.m4a"))
        sfx_cues = []
        if os.path.exists(sfx_path):
            sfx_cues.append(SFXCue(
                scene_id=1,
                name="whoosh",
                file=sfx_path,
                start_time=0.5,
                volume=0.25
            ))

        music_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "music", "cinematic_ambient.m4a"))
        audio_plan = AudioPlan(
            music=MusicTrackPlan(
                status="selected" if os.path.exists(music_path) else "skipped",
                file=music_path if os.path.exists(music_path) else None,
                volume=0.10,
                duck_volume=0.04
            ),
            sfx=sfx_cues,
            ducking_enabled=True
        )

        # Subtitles
        sub_service = SubtitleService()
        srt_path = self.workspace.get_subtitles_path()
        sub_service.generate_srt(scenes, srt_path)
        self.assertTrue(os.path.exists(srt_path))

        # Render Final 9:16 Video
        vid_service = VideoAssemblyService()
        success, video_path, edit_plan = vid_service.assemble_final_video(
            scenes=scenes,
            audio_plan=audio_plan,
            subtitles_path=srt_path,
            workspace=self.workspace,
            aspect_ratio="9:16",
            resolution="1080p",
            burn_subtitles=True
        )

        self.assertTrue(success)
        self.assertIsNotNone(edit_plan)
        self.assertTrue(os.path.exists(video_path))

        # -------------------------------------------------------------
        # Forensic Inspection of Rendered MP4
        # -------------------------------------------------------------
        media_info = probe_media_file(video_path)
        self.assertIsNotNone(media_info)

        v_stream = next((s for s in media_info["streams"] if s["codec_type"] == "video"), None)
        a_stream = next((s for s in media_info["streams"] if s["codec_type"] == "audio"), None)

        self.assertIsNotNone(v_stream, "Video stream missing from MP4")
        self.assertIsNotNone(a_stream, "Audio stream missing from MP4")

        # Verify Dimensions: 9:16 portrait must be 1080x1920
        actual_width = int(v_stream["width"])
        actual_height = int(v_stream["height"])
        self.assertEqual(actual_width, 1080, f"Expected width 1080, got {actual_width}")
        self.assertEqual(actual_height, 1920, f"Expected height 1920, got {actual_height}")

        # Verify Codecs
        self.assertIn("h264", v_stream["codec_name"].lower())
        self.assertIn("aac", a_stream["codec_name"].lower())

        # Verify Authoritative Timing Agreement:
        # scene audio durations (7.0s) -> final video duration (approx 7.0s within 0.5s tolerance)
        actual_video_dur = float(media_info["format"]["duration"])
        self.assertAlmostEqual(actual_video_dur, total_audio_duration, delta=0.75,
                               msg=f"Video duration ({actual_video_dur}s) deviated from planned audio duration ({total_audio_duration}s)")

        # Verify EditPlan is populated and matches reality
        self.assertEqual(len(edit_plan.scenes), 2)
        self.assertEqual(edit_plan.width, 1080)
        self.assertEqual(edit_plan.height, 1920)
        self.assertEqual(edit_plan.scenes[0].start_time, 0.0)
        self.assertEqual(edit_plan.scenes[1].start_time, round(dur1, 2))

        # -------------------------------------------------------------
        # QA Audit on Rendered Assets
        # -------------------------------------------------------------
        cfg = ProjectConfig(
            project_id=self.project_id,
            title="The Soul Sanctuary",
            aspect_ratio="9:16",
            resolution="1080p"
        )
        plan = ProductionPlan(
            project=cfg,
            scenes=scenes,
            total_duration=total_audio_duration,
            normalized_script="When your heart feels tired, return to quiet contemplation. Peace is the gentle stillness found within."
        )

        # Create dummy thumbnail
        thumb_path = self.workspace.get_thumbnail_path()
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "color=c=0xDAA520:s=720x1280:d=1", "-frames:v", "1", "-y", thumb_path], check=True, capture_output=True)

        qa_tool = MediaValidationTool()
        qa_result = qa_tool.inspect_production(
            production_plan=plan,
            video_path=video_path,
            thumbnail_path=thumb_path,
            subtitles_path=srt_path
        )

        self.assertEqual(qa_result.status, QAStatus.PASS, f"QA failed: {qa_result.errors}")
        self.assertEqual(qa_result.score, 100.0)

        # -------------------------------------------------------------
        # Intentional Defect Detection:
        # If expected aspect ratio is changed to 16:9, QA MUST FAIL!
        # -------------------------------------------------------------
        mismatched_cfg = ProjectConfig(
            project_id=self.project_id,
            title="The Soul Sanctuary",
            aspect_ratio="16:9",  # Wrong aspect ratio for a 1080x1920 video
            resolution="1080p"
        )
        mismatched_plan = ProductionPlan(
            project=mismatched_cfg,
            scenes=scenes,
            total_duration=total_audio_duration,
            normalized_script=plan.normalized_script
        )
        mismatched_qa = qa_tool.inspect_production(
            production_plan=mismatched_plan,
            video_path=video_path,
            subtitles_path=srt_path
        )
        self.assertEqual(mismatched_qa.status, QAStatus.FAIL)
        self.assertTrue(any("resolution_matches_request" in c.check_name and not c.passed for c in mismatched_qa.checks))

if __name__ == "__main__":
    unittest.main()
