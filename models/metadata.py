from typing import List, Optional
from .base import BaseModel, Field

class ThumbnailConcept(BaseModel):
    hook_concept: str = Field(..., description="The high-impact visual scene or metaphor")
    visual_prompt: str = Field(..., description="Cloudflare FLUX prompt for thumbnail base")
    overlay_text: str = Field(..., description="Short punchy 2-4 word high contrast text")
    accent_color: str = Field(default="#F59E0B", description="Hex color for emphasis/badges")

class YouTubeMetadata(BaseModel):
    title: str = Field(..., max_length=100, description="Compelling YouTube title")
    description: str = Field(..., description="Complete video description with timestamps and chapters")
    tags: List[str] = Field(default_factory=list, description="Targeted YouTube tags")
    category_id: str = Field(default="27", description="YouTube category (27: Education, 28: Science & Tech)")
    privacy_status: str = Field(default="private", description="private | unlisted | public")

class VideoPackaging(BaseModel):
    thumbnail_concept: ThumbnailConcept
    thumbnail_path: Optional[str] = None
    metadata: YouTubeMetadata
    published_video_id: Optional[str] = None
    published_url: Optional[str] = None
