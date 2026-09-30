import os
from typing import Dict, Any, Optional, Tuple, List
from utils.logging import get_logger
from utils.retry import retry_with_backoff, PermanentPipelineError, TransientPipelineError

logger = get_logger("youtube_tool")

class YouTubeUploadTool:
    """
    V2 Publishing Engine: Uploads finalized MP4, custom thumbnail, and metadata
    to YouTube via official YouTube Data API v3.
    """
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None
    ):
        self.client_id = client_id or os.environ.get("YOUTUBE_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("YOUTUBE_CLIENT_SECRET", "")
        self.refresh_token = refresh_token or os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def upload_video(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: List[str],
        thumbnail_path: Optional[str] = None,
        category_id: str = "27",
        privacy_status: str = "private"
    ) -> Dict[str, Any]:
        """
        Uploads video and custom thumbnail to YouTube.
        """
        if not os.path.exists(video_path):
            raise PermanentPipelineError(f"Video file not found for upload: {video_path}")

        # Check configuration
        if not self.is_configured():
            logger.warning("YouTube OAuth credentials not provided in secrets; executing dry-run simulation.")
            mock_video_id = f"yt_sim_{os.path.basename(video_path).split('.')[0]}"
            return {
                "success": True,
                "video_id": mock_video_id,
                "url": f"https://www.youtube.com/watch?v={mock_video_id}",
                "privacy_status": privacy_status,
                "mode": "simulation",
                "message": "Upload simulated successfully. Provide YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN for live channel publish."
            }

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            creds = Credentials(
                token=None,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=["https://www.googleapis.com/auth/youtube.upload"]
            )

            youtube = build("youtube", "v3", credentials=creds)

            body = {
                "snippet": {
                    "title": title[:100],
                    "description": description,
                    "tags": tags,
                    "categoryId": category_id
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(
                video_path,
                chunksize=1024 * 1024 * 8, # 8MB chunks
                resumable=True,
                mimetype="video/mp4"
            )

            logger.info(f"Initiating YouTube resumable upload for '{title}' (privacy={privacy_status})...")
            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"YouTube upload progress: {int(status.progress() * 100)}%")

            video_id = response.get("id")
            logger.info(f"Video uploaded successfully! Video ID: {video_id}")

            # Upload thumbnail if available
            if thumbnail_path and os.path.exists(thumbnail_path) and video_id:
                try:
                    logger.info(f"Uploading thumbnail: {thumbnail_path} for video {video_id}")
                    thumb_media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=thumb_media
                    ).execute()
                    logger.info("Custom thumbnail uploaded successfully.")
                except Exception as te:
                    logger.warning(f"Thumbnail upload failed (video still published): {te}")

            return {
                "success": True,
                "video_id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "privacy_status": privacy_status,
                "mode": "live",
                "message": "Video and metadata published to your YouTube channel successfully."
            }

        except Exception as e:
            logger.error(f"YouTube upload failure: {e}")
            raise TransientPipelineError(f"YouTube API error: {e}")
