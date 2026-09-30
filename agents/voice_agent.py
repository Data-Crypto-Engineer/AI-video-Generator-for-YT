from typing import List, Optional
from models.scene import Scene, SceneAudioResult
from services.audio_service import VoiceService
from utils.filesystem import WorkspaceManager
from utils.logging import get_logger

logger = get_logger("voice_agent")

class VoiceAgent:
    def __init__(self, voice_service: Optional[VoiceService] = None):
        self.voice_service = voice_service or VoiceService()

    def generate_all_narrations(
        self,
        scenes: List[Scene],
        workspace: WorkspaceManager,
        voice_name: str = "Kore",
        force_regenerate: bool = False
    ) -> List[SceneAudioResult]:
        logger.info(f"Voice Agent directing narration for {len(scenes)} scenes (voice={voice_name})...")
        results = self.voice_service.generate_all_narrations(
            scenes,
            workspace,
            voice_name=voice_name,
            force_regenerate=force_regenerate
        )
        successful = sum(1 for r in results if r.status == "completed")
        logger.info(f"Voice Agent completed: {successful}/{len(scenes)} scene audio files ready.")
        return results

    def retry_scene_narration(
        self,
        scene: Scene,
        workspace: WorkspaceManager,
        voice_name: str = "Kore"
    ) -> SceneAudioResult:
        logger.info(f"Voice Agent retrying narration for scene {scene.id}...")
        return self.voice_service.generate_scene_narration(
            scene,
            workspace,
            voice_name=voice_name,
            force_regenerate=True
        )
