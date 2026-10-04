from typing import Dict, Any, Optional
from models.scene import Scene, CameraMotion, TransitionType, VisualType
from models.production import ProductionPlan, ProjectConfig
from utils.gemini_client import GeminiReasoningClient
from utils.logging import get_logger

logger = get_logger("director_agent")

DIRECTOR_SYSTEM_INSTRUCTION = """
You are the Executive Video Director and Screenplay Architect for an automated broadcast video production studio.
Your task is to analyze the script and create a detailed, machine-readable production plan.

CORE DIRECTING RULES:
1. Divide the script into logical scenes (typically 3 to 7 scenes; each scene has 1 to 3 sentences, 15-35 words, 5-10 seconds duration).
2. VISUAL PROMPT DISCIPLINE:
   - The visual prompt must describe WHAT THE CAMERA SEES (subject, setting, lighting, camera framing, atmosphere).
   - NEVER simply copy narration text into the visual prompt.
   - For example:
     Narration: "The heart can remain young through creativity and love."
     Visual prompt: "A peaceful contemplative adult sitting beside a quiet lake at sunrise, gently sketching in an open notebook, warm golden morning light, tranquil natural water reflections, cinematic shallow depth of field, 35mm lens."
   - Avoid all literal text rendering, typography, subtitles, watermarks, or words on screen.
   - Maintain visual continuity and character consistency across scenes.
   - Frame for the requested aspect ratio:
     * 16:9: Wide cinematic landscape composition.
     * 9:16: Vertical portrait composition with centered subject and vertical depth.
3. VISUAL STYLE DIRECTION:
   - For 'The Soul Sanctuary' and contemplative themes: peaceful, cinematic, warm, contemplative, natural, spiritual, human, emotionally grounded, elegant, minimal, soft atmospheric lighting.
   - Do NOT force religious symbols into every scene. Choose naturally among nature, landscapes, human reflection, atmospheric light, architecture, or subtle symbolic visual storytelling.
4. CAMERA MOTION: Choose purposefully: 'slow_zoom_in', 'slow_zoom_out', 'pan_left', 'pan_right', or 'static'.
5. TRANSITIONS: 'crossfade' (smooth blend), 'fade' (subtle atmospheric fade), or 'cut'.
6. SOUND EFFECTS: Suggest subtle cinematic SFX cues where they heighten the visual ('whoosh', 'wind', 'impact', or empty list).
7. MUSIC MOOD: 'atmospheric', 'cinematic', 'peaceful', 'mystery', or 'space'.

Output MUST be strictly valid JSON matching this schema:
{
  "title": "string",
  "music_mood": "peaceful | atmospheric | cinematic | mystery | space",
  "scenes": [
    {
      "id": 1,
      "narration": "Exact text spoken in scene 1",
      "visual_prompt": "Hyper-detailed cinematic image description of camera view for FLUX",
      "duration": 6.5,
      "camera_motion": "slow_zoom_in",
      "transition": "crossfade",
      "music_mood": "peaceful",
      "sfx": ["whoosh"],
      "tone": "calm",
      "emotion": "contemplative"
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
        style: str = "The Soul Sanctuary (Peaceful & Spiritual)",
        voice_name: str = "Kore",
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
        original_script: str = "",
        script_warnings: Optional[list] = None
    ) -> ProductionPlan:
        logger.info(f"Director Agent analyzing script ({len(script)} chars), style='{style}', aspect_ratio={aspect_ratio}...")

        composition_note = "Wide cinematic horizontal composition (16:9)" if aspect_ratio == "16:9" else "Vertical mobile portrait composition with centered focal subject (9:16)"

        user_prompt = f"""
Script to direct:
\"\"\"
{script}
\"\"\"

Production parameters:
- Visual Style Direction: {style}
- Framing & Aspect Ratio: {aspect_ratio} ({composition_note})
- Narrator Voice: {voice_name}
- Target Resolution: {resolution}

Generate the complete scene-by-scene production plan in JSON.
Remember: The visual prompt must describe what the camera sees (subject, lighting, composition) and must NOT copy the narration text.
"""

        try:
            data = self.client.generate_json_response(user_prompt, DIRECTOR_SYSTEM_INSTRUCTION)
        except Exception as e:
            logger.warning(f"Gemini API returned error: {e}. Generating rule-based scene plan.")
            data = self._create_fallback_scene_plan(script, style, aspect_ratio)

        title = data.get("title", "Cinematic Reflection")
        music_mood = data.get("music_mood", "peaceful" if "Soul Sanctuary" in style else "atmospheric")
        raw_scenes = data.get("scenes", [])

        if not raw_scenes:
            raw_scenes = self._create_fallback_scene_plan(script, style, aspect_ratio).get("scenes", [])

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

            vis_prompt = s.get("visual_prompt", "").strip()
            if not vis_prompt or vis_prompt == narration:
                vis_prompt = self._generate_visual_description(narration, style, aspect_ratio, i)

            scene_obj = Scene(
                id=i,
                narration=narration,
                visual_prompt=vis_prompt,
                duration=s.get("duration", est_duration),
                visual_type=VisualType.GENERATED_IMAGE,
                camera_motion=motion,
                transition=transition,
                music_mood=s.get("music_mood", music_mood),
                sfx=s.get("sfx", []),
                tone=s.get("tone", "calm"),
                emotion=s.get("emotion", "contemplative"),
                start_time=round(total_duration, 2),
                end_time=round(total_duration + est_duration, 2)
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
            original_script=original_script or script,
            normalized_script=script,
            script_warnings=script_warnings or [],
            total_estimated_duration=round(total_duration, 1),
            total_duration=round(total_duration, 1)
        )

        logger.info(f"Director created production plan: {len(scenes)} scenes, est duration={total_duration:.1f}s")
        return plan

    def _generate_visual_description(self, narration: str, style: str, aspect_ratio: str, scene_idx: int) -> str:
        """Constructs camera-focused visual imagery that depicts scene emotion without repeating words."""
        framing = "wide cinematic landscape, 16:9 framing" if aspect_ratio == "16:9" else "vertical portrait framing, centered subject, 9:16 mobile composition"
        
        # Soul Sanctuary / spiritual / peaceful library of visual motifs
        motifs = [
            f"A solitary figure standing on a misty mountain overlook at dawn, golden sunlight breaking through clouds, tranquil atmosphere, soft atmospheric haze, {framing}",
            f"Calm ripples across a clear forest lake at sunset, warm amber light reflecting on water, gentle natural flora, peaceful cinematic depth of field, {framing}",
            f"Soft rays of morning light streaming through high arched stone windows onto a quiet reflective courtyard, elegant minimal architecture, warm dust motes in sunbeams, {framing}",
            f"Close-up of gentle hands holding a warm ceramic cup, soft ambient morning illumination, cozy rustic wooden surface, peaceful expression, shallow depth of field, {framing}",
            f"Vast rolling green meadows under a vast sky at twilight, gentle wind moving tall grasses, serene natural landscape, soft lavender and golden light, {framing}",
            f"An ancient olive tree standing under a serene canopy of stars and twilight, gentle warm breeze, quiet contemplation, cinematic natural realism, {framing}"
        ]
        
        selected_motif = motifs[(scene_idx - 1) % len(motifs)]
        return f"{selected_motif}, style of {style}, ultra realistic, natural color grading, no text, no subtitles, no watermarks"

    def _create_fallback_scene_plan(self, script: str, style: str, aspect_ratio: str = "16:9") -> Dict[str, Any]:
        """Splits script into sentences and creates descriptive camera prompts without duplicating text."""
        sentences = [s.strip() for s in script.replace("\n", " ").split(".") if len(s.strip()) > 5]
        if not sentences:
            sentences = [
                "When your heart feels tired, return to quiet contemplation and breathe.",
                "Peace is not the absence of storms, but the stillness found within."
            ]

        scenes_data = []
        chunk_size = 2
        for idx, i in enumerate(range(0, len(sentences), chunk_size), start=1):
            chunk = ". ".join(sentences[i:i+chunk_size]) + "."
            vis_prompt = self._generate_visual_description(chunk, style, aspect_ratio, idx)
            est_dur = round(max(5.0, len(chunk.split()) / 2.5), 1)

            scenes_data.append({
                "id": idx,
                "narration": chunk,
                "visual_prompt": vis_prompt,
                "duration": est_dur,
                "camera_motion": "slow_zoom_in" if idx % 2 != 0 else "slow_zoom_out",
                "transition": "crossfade" if idx > 1 else "cut",
                "music_mood": "peaceful" if "Soul Sanctuary" in style else "atmospheric",
                "sfx": ["whoosh"] if idx == 1 else ([] if idx % 2 == 0 else ["wind"]),
                "tone": "calm",
                "emotion": "contemplative"
            })

        return {
            "title": sentences[0][:60] if sentences else "The Soul Sanctuary",
            "music_mood": "peaceful" if "Soul Sanctuary" in style else "atmospheric",
            "scenes": scenes_data
        }
