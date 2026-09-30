from typing import Dict, Any, Optional
from models.metadata import VideoPackaging
from services.youtube_service import YouTubePublishService
from utils.logging import get_logger

logger = get_logger("youtube_agent")

class YouTubeAgent:
    """
    V2 Channel Distribution Agent: Publishes final MP4, custom thumbnail, and metadata
    to YouTube using OAuth 2.0 with safe defaults.
    """
    def __init__(self, publish_service: Optional[YouTubePublishService] = None):
        self.publish_service = publish_service or YouTubePublishService()

    def publish(
        self,
        video_path: str,
        packaging: VideoPackaging,
        privacy_status: str = "private"
    ) -> Dict[str, Any]:
        logger.info(f"YouTube Agent initiating upload (target privacy={privacy_status})...")
        return self.publish_service.publish_video(
            video_path=video_path,
            packaging=packaging,
            privacy_status=privacy_status
        )
