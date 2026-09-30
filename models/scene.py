from enum import Enum
from typing import List, Optional
from .base import BaseModel, Field

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

class VisualType(str, Enum):
    GENERATED_IMAGE = "generated_image"
    STOCK_IMAGE = "stock_image"
    LOCAL_ASSET = "local_asset"

class SceneStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class Scene(BaseModel):
    id: int = Field(..., description="1-indexed continuous scene number")
    narration: str = Field(..., description="Narration spoken in this scene")
    visual_prompt: str = Field(..., description="Photorealistic prompt for image synthesis")
    duration: float = Field(..., gt=0.0, description="Approximate or actual duration in seconds")
    visual_type: VisualType = Field(default=VisualType.GENERATED_IMAGE)
    camera_motion: CameraMotion = Field(default=CameraMotion.SLOW_ZOOM_IN)
    transition: TransitionType = Field(default=TransitionType.CROSSFADE)
    music_mood: str = Field(default="atmospheric", description="Musical vibe for this scene")
    sfx: List[str] = Field(default_factory=list, description="Cued sound effect names (e.g. whoosh, wind)")
    tone: str = Field(default="calm", description="Voice tone direction")
    emotion: str = Field(default="wonder", description="Emotional delivery")
    
    # Generated artifacts
    visual_path: Optional[str] = Field(default=None, description="Path to generated visual file")
    audio_path: Optional[str] = Field(default=None, description="Path to generated scene audio file")
    audio_duration: Optional[float] = Field(default=None, description="Exact probed audio duration")
    status: SceneStatus = Field(default=SceneStatus.PENDING)
    error: Optional[str] = Field(default=None)

class SceneVisualResult(BaseModel):
    scene_id: int
    status: str
    image_path: Optional[str] = None
    prompt_used: str
    error: Optional[str] = None
    retry_count: int = 0

class SceneAudioResult(BaseModel):
    scene_id: int
    status: str
    audio_path: Optional[str] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None
    retryable: bool = True
