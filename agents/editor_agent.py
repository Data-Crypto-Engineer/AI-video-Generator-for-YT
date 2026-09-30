from typing import List, Optional, Tuple
from models.scene import Scene
from models.audio import AudioPlan
from services.video_service import VideoAssemblyService
from services.subtitle_service import SubtitleService
from utils.filesystem import WorkspaceManager
from utils.logging import get_logger

logger = get_logger("editor_agent")

class EditorAgent:
    def __init__(
        self,
        video_service: Optional[VideoAssemblyService] = None,
        subtitle_service: Optional[SubtitleService] = None
    ):
        self.video_service = video_service or VideoAssemblyService()
        self.subtitle_service = subtitle_service or SubtitleService()

    def render_production(
        self,
        scenes: List[Scene],
        audio_plan: AudioPlan,
        workspace: WorkspaceManager,
        resolution: str = "1080p",
        burn_subtitles: bool = True
    ) -> Tuple[bool, str, str]:
        logger.info(f"Editor Agent starting video assembly for {len(scenes)} scenes ({resolution})...")

        # 1. Generate SRT subtitles
        subtitles_path = workspace.get_subtitles_path()
        self.subtitle_service.generate_srt(scenes, subtitles_path)

        # 2. Render final MP4 via FFmpeg
        success, video_path = self.video_service.assemble_final_video(
            scenes=scenes,
            audio_plan=audio_plan,
            subtitles_path=subtitles_path,
            workspace=workspace,
            resolution=resolution,
            burn_subtitles=burn_subtitles
        )

        if success:
            logger.info(f"Editor Agent render complete: {video_path}")
        else:
            logger.error(f"Editor Agent render failed: {video_path}")

        return success, video_path, subtitles_path
