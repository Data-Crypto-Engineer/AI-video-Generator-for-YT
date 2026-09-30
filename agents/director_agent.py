from typing import Dict, Any, Optional
from models.scene import Scene, CameraMotion, TransitionType, VisualType
from models.production import ProductionPlan, ProjectConfig
from utils.gemini_client import GeminiReasoningClient
from utils.logging import get_logger

logger = get_logger("director_agent")

DIRECTOR_SYSTEM_INSTRUCTION = """
You are the Executive Video Director and Screenplay Architect for an automated cinematic video production studio.
Your task is to analyze the user's script and create a detailed, machine-readable production plan.

Guidelines:
1. Divide the script into logical scenes (typically 3 to 7 scenes depending on length; each scene should have 1 to 3 sentences, around 15-35 words, 5-10 seconds duration).
2. For each scene, create a breathtaking, photorealistic visual prompt specifically optimized for Cloudflare FLUX Schnell (cinematic lighting, 8k documentary style, clear focal subject, rich textures, no text/watermarks).
3. Specify camera motion for each scene: 'slow_zoom_in', 'slow_zoom_out', 'pan_left', or 'pan_right'.
4. Specify transition: 'crossfade' or 'cut'.
5. Specify sound effects if beneficial ('whoosh', 'wind', 'impact', or empty list).
6. Set music mood: e.g. 'atmospheric', 'cinematic', 'mystery', 'space'.

Output MUST be strictly valid JSON with this schema:
{
  "title": "string",
  "music_mood": "atmospheric | cinematic | space | mystery",
  "scenes": [
    {
      "id": 1,
      "narration": "Exact text spoken in scene 1",
      "visual_prompt": "Hyper-detailed cinematic image description for FLUX",
      "duration": 7.0,
      "camera_motion": "slow_zoom_in",
      "transition": "crossfade",
      "music_mood": "atmospheric",
      "sfx": ["whoosh"],
      "tone": "calm",
      "emotion": "wonder"
    }
  ]
}
"""

class DirectorAgent:
    def __init__(self, reasoning_client: Optional[GeminiReasoningClient] = None):
        self.client = reasoning_client or GeminiReasoningClient()

    def create_production_plan(
        self,
        script: str,
        project_id: str,
        style: str = "Cinematic Documentary",
        voice_name: str = "Kore",
        aspect_ratio: str = "16:9",
        resolution: str = "1080p"
    ) -> ProductionPlan:
        logger.info(f"Director Agent analyzing script ({len(script)} chars), style='{style}'...")

        user_prompt = f"""
Script to direct:
\"\"\"
{script}
\"\"\"

Production parameters:
- Visual Style: {style}
- Narrator Voice: {voice_name}
- Aspect Ratio: {aspect_ratio}
- Target Resolution: {resolution}

Generate the complete scene-by-scene production plan in JSON.
"""

        try:
            data = self.client.generate_json_response(user_prompt, DIRECTOR_SYSTEM_INSTRUCTION)
        except Exception as e:
            logger.warning(f"Gemini API returned error: {e}. Generating rule-based scene plan.")
            data = self._create_fallback_scene_plan(script, style)

        title = data.get("title", "Cinematic Documentary")
        music_mood = data.get("music_mood", "atmospheric")
        raw_scenes = data.get("scenes", [])

        if not raw_scenes:
            raw_scenes = self._create_fallback_scene_plan(script, style).get("scenes", [])

        scenes = []
        total_duration = 0.0

        for i, s in enumerate(raw_scenes, start=1):
            narration = s.get("narration", "").strip() or f"Scene {i} narration."
            # Estimate duration: ~2.5 words per second
            word_count = len(narration.split())
            est_duration = max(4.0, round(word_count / 2.5, 1))

            motion_str = s.get("camera_motion", "slow_zoom_in")
            try:
                motion = CameraMotion(motion_str)
            except ValueError:
                motion = CameraMotion.SLOW_ZOOM_IN

            transition_str = s.get("transition", "crossfade")
            try:
                transition = TransitionType(transition_str)
            except ValueError:
                transition = TransitionType.CROSSFADE

            scene_obj = Scene(
                id=i,
                narration=narration,
                visual_prompt=s.get("visual_prompt", f"Cinematic {style} visual representing: {narration[:60]}"),
                duration=s.get("duration", est_duration),
                visual_type=VisualType.GENERATED_IMAGE,
                camera_motion=motion,
                transition=transition,
                music_mood=s.get("music_mood", music_mood),
                sfx=s.get("sfx", []),
                tone=s.get("tone", "calm"),
                emotion=s.get("emotion", "wonder")
            )
            scenes.append(scene_obj)
            total_duration += scene_obj.duration

        project_config = ProjectConfig(
            project_id=project_id,
            title=title,
            style=style,
            voice_name=voice_name,
            aspect_ratio=aspect_ratio,
            resolution=resolution
        )

        plan = ProductionPlan(
            project=project_config,
            scenes=scenes,
            music_mood=music_mood,
            total_estimated_duration=round(total_duration, 1)
        )

        logger.info(f"Director created production plan: {len(scenes)} scenes, total duration={total_duration:.1f}s")
        return plan

    def _create_fallback_scene_plan(self, script: str, style: str) -> Dict[str, Any]:
        """Splits script into paragraphs or sentences when LLM is offline or high demand."""
        sentences = [s.strip() for s in script.replace("\n", " ").split(".") if len(s.strip()) > 5]
        if not sentences:
            sentences = ["In the vast expanse of the cosmos, wonders await discovery.", "Every detail reveals a deeper mystery."]

        # Group 1-2 sentences per scene
        scenes_data = []
        chunk_size = 2
        for idx, i in enumerate(range(0, len(sentences), chunk_size), start=1):
            chunk = ". ".join(sentences[i:i+chunk_size]) + "."
            scenes_data.append({
                "id": idx,
                "narration": chunk,
                "visual_prompt": f"Cinematic documentary frame, {style}, ultra realistic 8k, majestic lighting: {chunk[:80]}",
                "duration": round(max(5.0, len(chunk.split()) / 2.5), 1),
                "camera_motion": "slow_zoom_in" if idx % 2 != 0 else "slow_zoom_out",
                "transition": "crossfade",
                "music_mood": "atmospheric",
                "sfx": ["whoosh"] if idx == 1 else [],
                "tone": "calm",
                "emotion": "wonder"
            })

        return {
            "title": sentences[0][:60] if sentences else "Cinematic Exploration",
            "music_mood": "atmospheric",
            "scenes": scenes_data
        }
