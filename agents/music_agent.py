from typing import List, Optional
from models.scene import Scene
from models.audio import AudioPlan
from services.audio_service import MusicSFXService
from utils.logging import get_logger

logger = get_logger("music_agent")

class MusicSFXAgent:
    def __init__(self, music_service: Optional[MusicSFXService] = None):
        self.music_service = music_service or MusicSFXService()

    def create_audio_plan(self, scenes: List[Scene], music_mood: str = "atmospheric") -> AudioPlan:
        logger.info(f"Music/SFX Agent evaluating audio plan for {len(scenes)} scenes (mood='{music_mood}')...")
        audio_plan = self.music_service.create_audio_plan(scenes, music_mood=music_mood)
        if audio_plan.music.status == "selected":
            logger.info(f"Music selected: {audio_plan.music.file}, ducking={audio_plan.ducking_enabled}")
        else:
            logger.info(f"Music status: not_found. Fallback advice provided.")
        return audio_plan
