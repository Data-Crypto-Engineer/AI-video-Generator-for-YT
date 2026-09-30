from typing import Dict, Any, Optional, List
from models.metadata import VideoPackaging, YouTubeMetadata
from tools.youtube_tool import YouTubeUploadTool
from utils.logging import get_logger

logger = get_logger("youtube_service")

class YouTubePublishService:
    def __init__(self, upload_tool: Optional[YouTubeUploadTool] = None):
        self.upload_tool = upload_tool or YouTubeUploadTool()

    def publish_video(
        self,
        video_path: str,
        packaging: VideoPackaging,
        privacy_status: Optional[str] = None
    ) -> Dict[str, Any]:
        meta = packaging.metadata
        privacy = privacy_status or meta.privacy_status or "private"

        logger.info(f"Publishing video to YouTube (privacy={privacy}): '{meta.title}'")

        result = self.upload_tool.upload_video(
            video_path=video_path,
            title=meta.title,
            description=meta.description,
            tags=meta.tags,
            thumbnail_path=packaging.thumbnail_path,
            category_id=meta.category_id,
            privacy_status=privacy
        )

        if result.get("success"):
            packaging.published_video_id = result.get("video_id")
            packaging.published_url = result.get("url")

        return result
