import unittest
from models.scene import Scene, CameraMotion, TransitionType, VisualType
from models.production import ProductionPlan, ProjectConfig, ProductionManifest
from models.audio import AudioPlan, MusicTrackPlan
from models.qa import QAResult, QAStatus, QACheckItem
from models.metadata import VideoPackaging, ThumbnailConcept, YouTubeMetadata

class TestSchemas(unittest.TestCase):
    def test_scene_schema_validation(self):
        scene = Scene(
            id=1,
            narration="In the beginning, stars formed from cosmic dust.",
            visual_prompt="Cinematic nebula glowing in deep space, 8k",
            duration=6.5,
            camera_motion=CameraMotion.SLOW_ZOOM_IN,
            transition=TransitionType.CROSSFADE,
            music_mood="space"
        )
        self.assertEqual(scene.id, 1)
        self.assertEqual(scene.duration, 6.5)
        self.assertEqual(scene.camera_motion, CameraMotion.SLOW_ZOOM_IN)
        self.assertEqual(scene.transition, TransitionType.CROSSFADE)

    def test_production_plan_schema(self):
        config = ProjectConfig(
            project_id="test-proj-123",
            title="Cosmic Wonders",
            style="Cinematic Documentary",
            voice_name="Kore",
            aspect_ratio="16:9",
            resolution="1080p"
        )
        scenes = [
            Scene(
                id=1,
                narration="First scene narration.",
                visual_prompt="A dramatic galaxy.",
                duration=5.0
            ),
            Scene(
                id=2,
                narration="Second scene narration.",
                visual_prompt="A supernova remnant.",
                duration=7.0
            )
        ]
        plan = ProductionPlan(
            project=config,
            scenes=scenes,
            music_mood="space",
            total_estimated_duration=12.0
        )
        self.assertEqual(len(plan.scenes), 2)
        self.assertEqual(plan.total_estimated_duration, 12.0)

    def test_qa_result_schema(self):
        checks = [
            QACheckItem(
                category="script",
                check_name="scene_ids_continuous",
                passed=True,
                details="Scene IDs 1-3 continuous",
                is_fatal=True
            ),
            QACheckItem(
                category="audio",
                check_name="narration_exists",
                passed=True,
                details="All audio files present",
                is_fatal=True
            )
        ]
        qa = QAResult(
            status=QAStatus.PASS,
            score=100.0,
            checks=checks
        )
        self.assertEqual(qa.status, QAStatus.PASS)
        self.assertEqual(qa.score, 100.0)

    def test_manifest_schema(self):
        config = ProjectConfig(
            project_id="proj-456",
            title="Test Production"
        )
        manifest = ProductionManifest(
            project_id="proj-456",
            script_hash="abc123hash",
            status="completed",
            config=config
        )
        dumped = manifest.model_dump()
        self.assertEqual(dumped["project_id"], "proj-456")
        self.assertEqual(dumped["status"], "completed")

if __name__ == "__main__":
    unittest.main()
