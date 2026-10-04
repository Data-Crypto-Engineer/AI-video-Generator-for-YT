from typing import Optional, List
from models.metadata import VideoPackaging, ThumbnailConcept, YouTubeMetadata
from models.production import ProductionPlan
from services.thumbnail_service import ThumbnailService
from utils.gemini_client import GeminiReasoningClient
from utils.filesystem import WorkspaceManager
from utils.logging import get_logger

logger = get_logger("thumbnail_agent")

THUMBNAIL_SYSTEM_INSTRUCTION = """
You are a YouTube Packaging Strategist and Thumbnail Designer for high-performing documentary and reflection channels.
Given the video title, style, and scene narrations, create tailored visual packaging:

1. THUMBNAIL HOOK:
   - Identify the single deepest emotional or curiosity hook in the script.
   - Describe a striking focal subject and composition (e.g. warm emotional expression, majestic sunrise mist, stunning solitary silhouette).
   - SHORT OVERLAY TEXT: 2 to 4 words MAX, ALL CAPS. Do NOT put the entire title on the thumbnail!
     * For "When Your Heart Feels Tired": "TIRED HEART?" or "FIND PEACE"
     * For ocean/space documentaries: "ALIEN OCEAN" or "EVENT HORIZON"
     * NEVER use generic placeholder clichés like "THE TRUTH" or "WATCH NOW" unless specifically appropriate.
2. YOUTUBE TITLE:
   - Compelling, honest, curiosity-inducing YouTube title (under 75 characters).
   - Sounds like a human creator, no spam or misleading clickbait.
3. DESCRIPTION:
   - Thoughtful 2-3 paragraph description summarizing the core message.
   - Timestamps and chapters matching scene durations.
4. TARGETED TAGS:
   - 8-12 highly relevant tags strictly related to the subject matter.
   - For 'The Soul Sanctuary' / spiritual topics: spiritual reflection, inner peace, mindfulness, healing, meditation, Islamic reminders.
   - For science/history: specific scientific topics, not generic tags. Avoid keyword stuffing.

Output strictly valid JSON matching this schema:
{
  "thumbnail_concept": {
    "hook_concept": "Focal emotional subject and lighting description",
    "visual_prompt": "Detailed FLUX prompt for thumbnail base image",
    "overlay_text": "SHORT TEXT (2-4 words, ALL CAPS)"
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
        scenes_summary = "\n".join([f"Scene {s.id} ({s.duration:.1f}s): {s.narration}" for s in production_plan.scenes])
        prompt = f"""
Project Title: {production_plan.project.title}
Visual Style: {production_plan.project.style}
Aspect Ratio: {production_plan.project.aspect_ratio}

Scene Breakdown:
{scenes_summary}

Formulate the thumbnail hook concept, punchy 2-4 word overlay text, and tailored YouTube metadata.
"""
        try:
            data = self.client.generate_json_response(prompt, THUMBNAIL_SYSTEM_INSTRUCTION)
        except Exception as e:
            logger.warning(f"Gemini metadata generation failed ({e}), using script-derived fallback packaging.")
            data = self._create_fallback_metadata(production_plan)

        t_data = data.get("thumbnail_concept", {})
        m_data = data.get("metadata", {})

        aspect_ratio = production_plan.project.aspect_ratio
        framing = "16:9 cinematic landscape" if aspect_ratio == "16:9" else "9:16 vertical portrait composition"

        concept = ThumbnailConcept(
            hook_concept=t_data.get("hook_concept", "Contemplative focal subject in warm golden light"),
            visual_prompt=t_data.get("visual_prompt", f"Cinematic emotional photography, {production_plan.project.style}, {framing}, soft natural lighting"),
            overlay_text=t_data.get("overlay_text", "FIND PEACE")[:24]
        )

        # Generate thumbnail image honoring aspect ratio
        success, thumb_path = self.thumbnail_service.generate_thumbnail(
            concept=concept,
            workspace=workspace,
            aspect_ratio=aspect_ratio
        )

        # Build chapters into description with authoritative timestamps
        chapters = []
        current_sec = 0.0
        for s in production_plan.scenes:
            dur = s.audio_duration or s.duration or 6.0
            mins = int(current_sec // 60)
            secs = int(current_sec % 60)
            clean_title = s.narration.split(".")[0][:45] if "." in s.narration else s.narration[:45]
            chapters.append(f"{mins:02d}:{secs:02d} - {clean_title}...")
            current_sec += dur

        chapters_str = "\n".join(chapters)
        base_desc = m_data.get("description", f"A peaceful, reflective exploration of {production_plan.project.title}.\n\nProduced with AI Video Production Agent.")
        
        # Tags tailored to style
        default_tags = ["mindfulness", "inner peace", "spiritual reflection", "the soul sanctuary", "healing"] if "Soul Sanctuary" in production_plan.project.style else ["documentary", "cinematic", "science", "exploration"]
        tags = m_data.get("tags") or default_tags

        full_desc = f"{base_desc}\n\nTIMESTAMPS & CHAPTERS:\n{chapters_str}\n\n{' '.join(['#' + t.replace(' ', '') for t in tags[:4]])}"

        metadata = YouTubeMetadata(
            title=m_data.get("title", production_plan.project.title)[:100],
            description=full_desc,
            tags=tags[:15],
            category_id=m_data.get("category_id", "27"),
            privacy_status="private"
        )

        return VideoPackaging(
            thumbnail_concept=concept,
            thumbnail_path=thumb_path if success else None,
            metadata=metadata
        )

    def _create_fallback_metadata(self, plan: ProductionPlan) -> dict:
        """Generates script-aware fallback metadata without generic placeholders."""
        first_scene = plan.scenes[0].narration if plan.scenes else plan.project.title
        is_spiritual = any(w in first_scene.lower() for w in ["heart", "peace", "soul", "calm", "prayer", "god", "allah", "stillness", "tired"])

        if is_spiritual:
            return {
                "thumbnail_concept": {
                    "hook_concept": "A serene person resting by tranquil water at sunrise, golden light, deep inner calm",
                    "visual_prompt": f"Cinematic photography of a peaceful person in contemplative stillness, soft morning mist, amber light, {plan.project.style}",
                    "overlay_text": "TIRED HEART?"
                },
                "metadata": {
                    "title": f"When Your Heart Feels Tired | A Moment of Peace",
                    "description": f"In a world that constantly demands more, take a breath and return to quiet contemplation.\n\n{plan.project.title}",
                    "tags": ["inner peace", "spiritual reflection", "mindfulness", "healing", "the soul sanctuary", "peaceful contemplation"],
                    "category_id": "27"
                }
            }
        else:
            return {
                "thumbnail_concept": {
                    "hook_concept": f"A breathtaking wide perspective of {plan.project.title}, atmospheric lighting",
                    "visual_prompt": f"Cinematic documentary frame of {plan.project.title}, majestic volumetric lighting, 8k ultra realism",
                    "overlay_text": "BEYOND LIMITS"
                },
                "metadata": {
                    "title": f"The Hidden Wonder of {plan.project.title}",
                    "description": f"An immersive exploration into the wonders of {plan.project.title}.",
                    "tags": ["documentary", "exploration", "nature", "science", "cinematic"],
                    "category_id": "27"
                }
            }
