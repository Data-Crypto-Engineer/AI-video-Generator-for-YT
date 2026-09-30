import os
from typing import Dict, Any, Optional
from agents import (
    DirectorAgent,
    VisualAgent,
    VoiceAgent,
    MusicSFXAgent,
    EditorAgent,
    QAAgent,
    ThumbnailAgent,
    YouTubeAgent,
)
from utils.logging import get_logger

logger = get_logger("crew_factory")

class VideoProductionCrew:
    """
    Crew organizing the 8 specialized production agents.
    Agents handle creative choices, scene planning, prompt engineering,
    audio direction, forensic QA, packaging, and distribution.
    Deterministic Python services handle HTTP, FFmpeg, and file I/O.
    """
    def __init__(self):
        self.director = DirectorAgent()
        self.visual = VisualAgent()
        self.voice = VoiceAgent()
        self.music = MusicSFXAgent()
        self.editor = EditorAgent()
        self.qa = QAAgent()
        self.thumbnail = ThumbnailAgent()
        self.youtube = YouTubeAgent()

    def get_agent_summary(self) -> Dict[str, str]:
        return {
            "Director": "Decomposes raw screenplay into scene blueprints, camera motion, and timing.",
            "Visual": "Generates scene visuals with Cloudflare Workers AI FLUX Schnell.",
            "Voice": "Directs natural narration speech using Google Gemini 3.8 Flash-Lite TTS.",
            "Music/SFX": "Formulates structured audio plan with licensed music and ducking curves.",
            "Editor": "Assembles visuals, Ken Burns motion, narration, ducked music, and subtitles via FFmpeg.",
            "QA": "Forensically audits streams, codecs, resolution, and manifest with ffprobe.",
            "Thumbnail": "Generates high-CTR 16:9 thumbnail and YouTube SEO metadata.",
            "YouTube": "Publishes final MP4, custom thumbnail, and metadata via YouTube Data API v3 (V2)."
        }
