from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

class CameraMotion(str, Enum):
    SLOW_ZOOM_IN = "slow_zoom_in"
    SLOW_ZOOM_OUT = "slow_zoom_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    STATIC = "static"

class TransitionType(str, Enum):
    CUT = "cut"
    CROSSFADE = "crossfade"
    DISSOLVE = "dissolve"
    FADE_TO_BLACK = "fade_to_black"

class SceneStatus(str, Enum):
    PENDING = "pending"
    AUDIO_READY = "audio_ready"
    VISUAL_READY = "visual_ready"
    COMPLETED = "completed"
    FAILED = "failed"

class Scene(BaseModel):
    id: int
    narration: str
    visual_prompt: str
    duration: float
    start_time: float = 0.0
    end_time: float = 0.0
    camera_motion: CameraMotion = CameraMotion.SLOW_ZOOM_IN
    transition: TransitionType = TransitionType.CUT
    audio_path: Optional[str] = None
    visual_path: Optional[str] = None
    audio_duration: Optional[float] = None
    status: SceneStatus = SceneStatus.PENDING
    error: Optional[str] = None
    visual_source: Optional[str] = "Cloudflare FLUX"
    quota_exhausted: bool = False

    class Config:
        extra = "allow"  # Allows extra attributes without Pydantic validation errors

class SceneAudioResult(BaseModel):
    scene_id: int
    status: str
    audio_path: Optional[str] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None
    retryable: bool = False

    class Config:
        extra = "allow"

class SceneVisualResult(BaseModel):
    scene_id: int
    status: str
    image_path: Optional[str] = None
    prompt_used: Optional[str] = None
    error: Optional[str] = None

    class Config:
        extra = "allow"
