from typing import Optional, List
from models.metadata import VideoPackaging, ThumbnailConcept, YouTubeMetadata
from models.production import ProductionPlan
from services.thumbnail_service import ThumbnailService
from utils.gemini_client import GeminiReasoningClient
from utils.filesystem import WorkspaceManager
from utils.logging import get_logger

logger = get_logger("thumbnail_agent")

THUMBNAIL_SYSTEM_INSTRUCTION = """
You are a YouTube Packaging Strategist and Thumbnail Designer.
Given the video title and scene narrations, create:
1. A punchy thumbnail hook concept and detailed image prompt for Cloudflare FLUX (dramatic, vibrant, high CTR, 16:9).
2. A short, bold 2-4 word thumbnail overlay text (e.g. "WHAT HAPPENED?", "LOST HORIZON", "DEEP SECRET", "BEYOND REALITY").
3. An optimized YouTube title (under 70 chars, curiosity-inducing, no misleading claims).
4. A rich YouTube description with chapters/timestamps and SEO keywords.
5. 8-12 relevant YouTube tags.

Output strictly valid JSON matching this schema:
{
  "thumbnail_concept": {
    "hook_concept": "string",
    "visual_prompt": "string",
    "overlay_text": "string (2-4 words, ALL CAPS)"
  },
  "metadata": {
    "title": "string",
    "description": "string",
    "tags": ["tag1", "tag2"],
    "category_id": "27"
  }
}
"""

class ThumbnailAgent:
    def __init__(
        self,
        thumbnail_service: Optional[ThumbnailService] = None,
        reasoning_client: Optional[GeminiReasoningClient] = None
    ):
        self.thumbnail_service = thumbnail_service or ThumbnailService()
        self.client = reasoning_client or GeminiReasoningClient()

    def package_video(
        self,
        production_plan: ProductionPlan,
        workspace: WorkspaceManager
    ) -> VideoPackaging:
        logger.info("Thumbnail Agent formulating visual packaging and YouTube metadata...")

        # Build context from scenes
        scenes_summary = "\n".join([f"Scene {s.id}: {s.narration}" for s in production_plan.scenes])
        prompt = f"""
Project Title: {production_plan.project.title}
Visual Style: {production_plan.project.style}

Scene Narrations:
{scenes_summary}

Formulate the thumbnail concept, overlay text, and YouTube metadata.
"""
        try:
            data = self.client.generate_json_response(prompt, THUMBNAIL_SYSTEM_INSTRUCTION)
        except Exception as e:
            logger.warning(f"Gemini metadata generation failed ({e}), using default packaging.")
            data = self._create_fallback_metadata(production_plan)

        t_data = data.get("thumbnail_concept", {})
        m_data = data.get("metadata", {})

        concept = ThumbnailConcept(
            hook_concept=t_data.get("hook_concept", "Dramatic focal moment"),
            visual_prompt=t_data.get("visual_prompt", f"Cinematic {production_plan.project.style} wide angle, dramatic lighting: {production_plan.project.title}"),
            overlay_text=t_data.get("overlay_text", "UNSEEN REALITY")[:24]
        )

        # Generate thumbnail image
        success, thumb_path = self.thumbnail_service.generate_thumbnail(concept, workspace)

        # Build chapters into description
        chapters = []
        current_sec = 0.0
        for s in production_plan.scenes:
            dur = s.audio_duration or s.duration or 6.0
            mins = int(current_sec // 60)
            secs = int(current_sec % 60)
            chapters.append(f"{mins:02d}:{secs:02d} Scene {s.id}")
            current_sec += dur

        chapters_str = "\n".join(chapters)
        base_desc = m_data.get("description", f"Explore {production_plan.project.title} in this documentary.\n\nProduced with AI Video Production Agent.")
        full_desc = f"{base_desc}\n\nTIMESTAMPS:\n{chapters_str}\n\n#documentary #cinematic #education"

        metadata = YouTubeMetadata(
            title=m_data.get("title", production_plan.project.title)[:100],
            description=full_desc,
            tags=m_data.get("tags", ["documentary", "cinematic", "science", "nature", "history"]),
            category_id=m_data.get("category_id", "27"),
            privacy_status="private"
        )

        return VideoPackaging(
            thumbnail_concept=concept,
            thumbnail_path=thumb_path if success else None,
            metadata=metadata
        )

    def _create_fallback_metadata(self, plan: ProductionPlan) -> dict:
        return {
            "thumbnail_concept": {
                "hook_concept": "Dramatic focal subject",
                "visual_prompt": f"Cinematic 8k documentary frame of {plan.project.title}, volumetric lighting",
                "overlay_text": "THE TRUTH"
            },
            "metadata": {
                "title": f"The Story of {plan.project.title}",
                "description": f"An exclusive deep-dive into {plan.project.title}.",
                "tags": ["documentary", "cinematic", "education", "ai"],
                "category_id": "27"
            }
        }
