from typing import List, Optional
from .base import BaseModel, Field

class MusicTrackPlan(BaseModel):
    status: str = Field(default="selected", description="selected | not_found | disabled")
    file: Optional[str] = Field(default=None, description="Path to verified audio track")
    source: str = Field(default="local_royalty_free", description="Provider or source")
    license: str = Field(default="Creative Commons Zero / Royalty-Free Built-in", description="License identifier")
    commercial_use_allowed: bool = True
    youtube_use_allowed: bool = True
    attribution_required: bool = False
    start: float = Field(default=0.0, description="Start offset in seconds")
    end: Optional[float] = Field(default=None, description="End offset in seconds")
    volume: float = Field(default=0.10, ge=0.0, le=1.0, description="Baseline background volume")
    duck_volume: float = Field(default=0.06, ge=0.0, le=1.0, description="Volume during narration")
    fade_in: float = Field(default=2.0, ge=0.0)
    fade_out: float = Field(default=3.0, ge=0.0)
    loop: bool = Field(default=True)

class SFXCue(BaseModel):
    scene_id: int
    name: str
    file: str
    source: str = "local_royalty_free"
    license: str = "Royalty-Free / Studio Synthesized"
    commercial_use_allowed: bool = True
    youtube_use_allowed: bool = True
    attribution_required: bool = False
    start_time: float
    volume: float = Field(default=0.18, ge=0.0, le=1.0)
    fade_in: float = 0.2
    fade_out: float = 0.5

class MusicFallbackRecommendation(BaseModel):
    suggested_theme: str
    suggested_style: str
    reason: str
    suggestion_links: List[str] = Field(default_factory=list)

class AudioPlan(BaseModel):
    music: MusicTrackPlan
    sfx: List[SFXCue] = Field(default_factory=list)
    fallback: Optional[MusicFallbackRecommendation] = None
    ducking_enabled: bool = True
