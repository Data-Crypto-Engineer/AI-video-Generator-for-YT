import os
from typing import List, Optional, Tuple, Dict, Any
from models.scene import Scene, SceneAudioResult
from models.audio import AudioPlan, MusicTrackPlan, SFXCue, MusicFallbackRecommendation
from tools.gemini_tts_tool import TTSProvider, GeminiTTSProvider
from utils.filesystem import WorkspaceManager
from utils.logging import get_logger
from utils.validation import validate_wav_audio, get_audio_duration

logger = get_logger("audio_service")

ASSETS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))
MUSIC_DIR = os.path.join(ASSETS_DIR, "music")
SFX_DIR = os.path.join(ASSETS_DIR, "sfx")

class VoiceService:
    def __init__(self, provider: Optional[TTSProvider] = None):
        self.provider = provider or GeminiTTSProvider()

    def generate_scene_narration(
        self,
        scene: Scene,
        workspace: WorkspaceManager,
        voice_name: str = "Kore",
        force_regenerate: bool = False
    ) -> SceneAudioResult:
        output_path = workspace.get_scene_audio_path(scene.id)

        # Check existing cached audio
        if not force_regenerate:
            valid, _ = validate_wav_audio(output_path)
            if valid:
                dur = get_audio_duration(output_path) or scene.duration
                logger.info(f"Reusing cached narration for scene {scene.id:02d}: {output_path} ({dur:.2f}s)")
                scene.audio_path = output_path
                scene.audio_duration = dur
                scene.duration = dur  # Authoritative timeline update
                return SceneAudioResult(
                    scene_id=scene.id,
                    status="completed",
                    audio_path=output_path,
                    duration_seconds=dur
                )

        logger.info(f"Generating narration for scene {scene.id:02d} (voice={voice_name}): '{scene.narration[:50]}...'")
        style = f"Warm, calm, mature documentary narration. Tone: {scene.tone}. Emotion: {scene.emotion}."

        try:
            success, path, duration = self.provider.generate_speech(
                text=scene.narration,
                output_path=output_path,
                voice_name=voice_name,
                style_direction=style
            )
            scene.audio_path = path
            scene.audio_duration = duration
            scene.duration = duration  # Authoritative timeline update
            return SceneAudioResult(
                scene_id=scene.id,
                status="completed",
                audio_path=path,
                duration_seconds=duration
            )
        except Exception as e:
            logger.error(f"TTS generation failed for scene {scene.id:02d}: {e}")
            scene.error = str(e)
            return SceneAudioResult(
                scene_id=scene.id,
                status="failed",
                audio_path=None,
                duration_seconds=0.0,
                error=str(e),
                retryable=True
            )

    def generate_all_narrations(
        self,
        scenes: List[Scene],
        workspace: WorkspaceManager,
        voice_name: str = "Kore",
        force_regenerate: bool = False
    ) -> List[SceneAudioResult]:
        results = []
        for scene in scenes:
            res = self.generate_scene_narration(scene, workspace, voice_name=voice_name, force_regenerate=force_regenerate)
            results.append(res)
        return results

class MusicSFXService:
    """
    Formulates a structured AudioPlan with licensed music and sound effects.
    Never fails the pipeline if music cannot be found; creates a verified fallback recommendation.
    """
    MOOD_TO_TRACK_MAP = {
        "atmospheric": "atmospheric_documentary.m4a",
        "documentary": "atmospheric_documentary.m4a",
        "cinematic": "cinematic_ambient.m4a",
        "space": "deep_space_drone.m4a",
        "mystery": "subtle_tension.m4a",
        "tension": "subtle_tension.m4a",
        "calm": "cinematic_ambient.m4a",
        "default": "atmospheric_documentary.m4a"
    }

    SFX_MAP = {
        "whoosh": "whoosh.m4a",
        "wind": "wind_ambience.m4a",
        "impact": "deep_hit.m4a",
        "hit": "deep_hit.m4a"
    }

    def create_audio_plan(self, scenes: List[Scene], music_mood: str = "atmospheric") -> AudioPlan:
        # 1. Match music track
        norm_mood = music_mood.lower().strip()
        matched_filename = None
        for key, fname in self.MOOD_TO_TRACK_MAP.items():
            if key in norm_mood:
                matched_filename = fname
                break
        if not matched_filename:
            matched_filename = self.MOOD_TO_TRACK_MAP["default"]

        music_file_path = os.path.join(MUSIC_DIR, matched_filename)
        music_plan = None
        fallback = None

        if os.path.exists(music_file_path):
            logger.info(f"Matched royalty-free music track: {matched_filename} for mood '{music_mood}'")
            music_plan = MusicTrackPlan(
                status="selected",
                file=music_file_path,
                source="local_verified_library",
                license="Royalty-Free / Studio Synthesized (Commercial & YouTube Safe)",
                commercial_use_allowed=True,
                youtube_use_allowed=True,
                attribution_required=False,
                start=0.0,
                volume=0.10,
                duck_volume=0.06,
                fade_in=2.0,
                fade_out=3.0,
                loop=True
            )
        else:
            logger.warning(f"Music track not found at {music_file_path}; setting status to 'skipped' and creating recommendation.")
            music_plan = MusicTrackPlan(
                status="skipped",
                file=None
            )
            fallback = MusicFallbackRecommendation(
                suggested_theme=f"Soft atmospheric ambient piano for '{music_mood}'",
                suggested_style="Minimal ambient cinematic drone, soft acoustic piano, subtle synth pad, no vocals.",
                tempo="slow",
                instrumentation="soft piano + subtle pad",
                reason="No matching verified audio file in local library; continuing without background music to avoid copyright infringement.",
                suggestion_links=[
                    "https://studio.youtube.com/channel/music (YouTube Audio Library - Free & Monetization Safe)",
                    "https://freemusicarchive.org (Free Music Archive CC-BY)",
                    "https://incompetech.com (Kevin MacLeod Royalty Free)"
                ]
            )

        # 2. Match SFX cues across scene timeline
        sfx_cues: List[SFXCue] = []
        for scene in scenes:
            dur = scene.audio_duration or scene.duration or 6.0
            start_t = getattr(scene, "start_time", 0.0)
            if scene.sfx:
                for sfx_name in scene.sfx:
                    norm_sfx = sfx_name.lower().strip()
                    sfx_filename = self.SFX_MAP.get(norm_sfx)
                    if sfx_filename:
                        sfx_path = os.path.join(SFX_DIR, sfx_filename)
                        if os.path.exists(sfx_path):
                            sfx_cues.append(SFXCue(
                                scene_id=scene.id,
                                name=norm_sfx,
                                file=sfx_path,
                                start_time=round(start_t + 0.3, 2),
                                volume=0.22
                            ))

        return AudioPlan(
            music=music_plan,
            sfx=sfx_cues,
            fallback=fallback,
            ducking_enabled=True
        )
