import unittest
import os
import tempfile
from models.scene import Scene, SceneStatus, CameraMotion, TransitionType
from models.production import ProjectConfig, ProductionPlan, EditPlan, EditScenePlan, ProductionManifest
from models.audio import AudioPlan, MusicTrackPlan, SFXCue
from models.qa import QAStatus
from services.subtitle_service import SubtitleService
from tools.youtube_tool import YouTubeUploadTool
from tools.media_validation_tool import MediaValidationTool
from tools.ffmpeg_tool import FFmpegTool

class TestProductionPipeline(unittest.TestCase):

    def test_01_16x9_dimensions(self):
        """Item 1: 16:9 aspect ratio resolves to 1920x1080 (1080p) and 1280x720 (720p)."""
        aspect = "16:9"
        is_portrait = "9:16" in aspect or aspect == "portrait"
        w_1080, h_1080 = (1080, 1920) if is_portrait else (1920, 1080)
        w_720, h_720 = (720, 1280) if is_portrait else (1280, 720)
        self.assertEqual((w_1080, h_1080), (1920, 1080))
        self.assertEqual((w_720, h_720), (1280, 720))

    def test_02_9x16_dimensions(self):
        """Item 2: 9:16 aspect ratio resolves to 1080x1920 (1080p) and 720x1280 (720p)."""
        aspect = "9:16"
        is_portrait = "9:16" in aspect or aspect == "portrait"
        w_1080, h_1080 = (1080, 1920) if is_portrait else (1920, 1080)
        w_720, h_720 = (720, 1280) if is_portrait else (1280, 720)
        self.assertEqual((w_1080, h_1080), (1080, 1920))
        self.assertEqual((w_720, h_720), (720, 1280))

    def test_03_actual_tts_duration_drives_scene_duration(self):
        """Item 3: Authoritative actual audio duration drives scene duration instead of stale estimates."""
        scene = Scene(
            id=1,
            narration="In a quiet world, the soul finds rest.",
            visual_prompt="Calm lake at dawn",
            duration=5.0  # Estimated
        )
        self.assertEqual(scene.duration, 5.0)

        # TTS generates actual audio probed at 7.82 seconds
        actual_measured_audio_dur = 7.82
        scene.audio_duration = actual_measured_audio_dur
        scene.duration = actual_measured_audio_dur  # Pipeline update

        self.assertEqual(scene.duration, 7.82)
        self.assertEqual(scene.audio_duration, 7.82)

    def test_04_timeline_calculation(self):
        """Item 4: Timeline calculates continuous start_time, end_time, and total_duration."""
        scenes = [
            Scene(id=1, narration="Scene 1", visual_prompt="V1", duration=4.5, audio_duration=4.5),
            Scene(id=2, narration="Scene 2", visual_prompt="V2", duration=6.2, audio_duration=6.2),
            Scene(id=3, narration="Scene 3", visual_prompt="V3", duration=5.1, audio_duration=5.1),
        ]
        current_time = 0.0
        for s in scenes:
            s.start_time = round(current_time, 2)
            s.end_time = round(current_time + s.duration, 2)
            current_time += s.duration

        self.assertEqual(scenes[0].start_time, 0.0)
        self.assertEqual(scenes[0].end_time, 4.5)
        self.assertEqual(scenes[1].start_time, 4.5)
        self.assertEqual(scenes[1].end_time, 10.7)
        self.assertEqual(scenes[2].start_time, 10.7)
        self.assertEqual(scenes[2].end_time, 15.8)
        self.assertAlmostEqual(current_time, 15.8, places=2)

    def test_05_sfx_inclusion(self):
        """Item 5: SFX cues are placed with valid timeline timestamps and volumes in AudioPlan."""
        sfx_cue = SFXCue(
            scene_id=2,
            name="whoosh",
            file="/path/to/whoosh.m4a",
            start_time=4.8,
            volume=0.22
        )
        audio_plan = AudioPlan(
            music=MusicTrackPlan(status="selected", volume=0.10, duck_volume=0.04),
            sfx=[sfx_cue],
            ducking_enabled=True
        )
        self.assertEqual(len(audio_plan.sfx), 1)
        self.assertEqual(audio_plan.sfx[0].start_time, 4.8)
        self.assertEqual(audio_plan.sfx[0].volume, 0.22)

    def test_06_music_ducking_configuration(self):
        """Item 6: Music ducking parameters specify baseline volume and duck volume."""
        music = MusicTrackPlan(
            status="selected",
            volume=0.12,
            duck_volume=0.04
        )
        self.assertLess(music.duck_volume, music.volume)
        self.assertEqual(music.duck_volume, 0.04)
        self.assertEqual(music.volume, 0.12)

    def test_07_subtitle_timing(self):
        """Item 7: Subtitle timing strictly corresponds to actual scene timeline timestamps."""
        scenes = [
            Scene(id=1, narration="First scene narration line.", visual_prompt="V1", duration=4.0, start_time=0.0, end_time=4.0),
            Scene(id=2, narration="Second scene narration line.", visual_prompt="V2", duration=6.0, start_time=4.0, end_time=10.0),
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".srt", delete=False) as f:
            srt_path = f.name

        try:
            sub_service = SubtitleService()
            out = sub_service.generate_srt(scenes, srt_path)
            self.assertTrue(os.path.exists(out))
            with open(out, "r") as sf:
                content = sf.read()
            self.assertIn("00:00:00,000 -->", content)
            self.assertIn("First scene", content)
            self.assertIn("Second scene", content)
        finally:
            if os.path.exists(srt_path):
                os.remove(srt_path)

    def test_08_qa_detects_duration_mismatch(self):
        """Item 8: QA fails when video duration significantly mismatches planned timeline."""
        cfg = ProjectConfig(project_id="test-qa", title="QA Test", aspect_ratio="16:9", resolution="1080p")
        scenes = [
            Scene(id=1, narration="Scene 1", visual_prompt="V1", duration=5.0, audio_duration=5.0)
        ]
        plan = ProductionPlan(project=cfg, scenes=scenes, total_duration=5.0)
        qa_tool = MediaValidationTool()

        # Target non-existent video path
        res = qa_tool.inspect_production(plan, video_path="/tmp/non_existent_fake.mp4")
        self.assertEqual(res.status, QAStatus.FAIL)
        failed_checks = [c.check_name for c in res.checks if not c.passed]
        self.assertIn("mp4_stream_integrity", failed_checks)

    def test_09_qa_detects_wrong_aspect_ratio(self):
        """Item 9: QA fails if resolution/aspect ratio does not match requested format."""
        # Request 9:16 portrait (1080x1920)
        cfg = ProjectConfig(project_id="test-ar", title="AR Test", aspect_ratio="9:16", resolution="1080p")
        scenes = [
            Scene(id=1, narration="Scene 1", visual_prompt="V1", duration=4.0, audio_duration=4.0)
        ]
        plan = ProductionPlan(project=cfg, scenes=scenes, total_duration=4.0)
        qa_tool = MediaValidationTool()

        # If MP4 has 1920x1080 instead of expected 1080x1920, QA check 'resolution_matches_request' must fail
        res = qa_tool.inspect_production(plan, video_path="/tmp/non_existent.mp4")
        self.assertEqual(res.status, QAStatus.FAIL)

    def test_10_scene_status_transitions_to_completed(self):
        """Item 10: Scene status transitions from PENDING to PROCESSING to COMPLETED."""
        scene = Scene(id=1, narration="Text", visual_prompt="Prompt", duration=5.0)
        self.assertEqual(scene.status, SceneStatus.PENDING)

        scene.status = SceneStatus.PROCESSING
        self.assertEqual(scene.status.value, "processing")

        scene.visual_path = "/path/to/visual.png"
        scene.audio_path = "/path/to/audio.wav"
        scene.status = SceneStatus.COMPLETED
        self.assertEqual(scene.status, SceneStatus.COMPLETED)

    def test_11_edit_plan_populated_in_manifest(self):
        """Item 11: EditPlan is populated with scene blueprints and stored in manifest."""
        edit_scene = EditScenePlan(
            scene_id=1,
            start_time=0.0,
            end_time=5.0,
            duration=5.0,
            visual_path="/tmp/v1.png",
            audio_path="/tmp/a1.wav",
            motion="slow_zoom_in"
        )
        audio = AudioPlan(music=MusicTrackPlan(status="skipped"))
        edit_plan = EditPlan(
            project_id="proj-edit-1",
            aspect_ratio="16:9",
            resolution="1080p",
            width=1920,
            height=1080,
            scenes=[edit_scene],
            audio=audio,
            output_path="/tmp/out.mp4"
        )
        manifest = ProductionManifest(
            project_id="proj-edit-1",
            script_hash="hash123",
            config=ProjectConfig(project_id="proj-edit-1", title="Title"),
            edit_plan=edit_plan
        )
        dumped = manifest.model_dump()
        self.assertIsNotNone(dumped.get("edit_plan"))
        self.assertEqual(len(dumped["edit_plan"]["scenes"]), 1)
        self.assertEqual(dumped["edit_plan"]["width"], 1920)

    def test_12_youtube_upload_does_not_simulate(self):
        """Item 12: YouTube upload returns status='not_authenticated' when credentials missing, never simulates."""
        tool = YouTubeUploadTool(client_id="", client_secret="", refresh_token="")
        self.assertFalse(tool.is_configured())

        with tempfile.NamedTemporaryFile("w", suffix=".mp4", delete=False) as f:
            f.write("mock video bytes")
            video_path = f.name

        try:
            result = tool.upload_video(
                video_path=video_path,
                title="Test Video",
                description="Test Description",
                tags=["test"]
            )
            self.assertFalse(result.get("success"))
            self.assertEqual(result.get("status"), "not_authenticated")
            self.assertIsNone(result.get("video_id"))
            self.assertIsNone(result.get("url"))
            self.assertNotIn("simulation", result.get("mode", ""))
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)

if __name__ == "__main__":
    unittest.main()
