from typing import List, Dict, Any, Optional
from datetime import datetime
from .base import BaseModel, Field
from .scene import Scene
from .audio import AudioPlan
from .qa import QAResult
from .metadata import VideoPackaging

class ProjectConfig(BaseModel):
    project_id: str
    title: str
    style: str = "Cinematic Documentary"
    voice_name: str = "Kore"
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class ProductionPlan(BaseModel):
    project: ProjectConfig
    scenes: List[Scene]
    music_mood: str = "atmospheric"
    total_estimated_duration: float = 0.0

class EditScenePlan(BaseModel):
    scene_id: int
    start_time: float
    end_time: float
    duration: float
    visual_path: str
    audio_path: str
    motion: str
    transition_in: str = "cut"
    transition_out: str = "crossfade"

class EditPlan(BaseModel):
    project_id: str
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    scenes: List[EditScenePlan]
    audio: AudioPlan
    subtitles_file: Optional[str] = None
    output_path: str

class ProductionManifest(BaseModel):
    project_id: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    script_hash: str
    status: str = "in_progress" # in_progress | completed | failed
    stage: str = "init"
    config: ProjectConfig
    plan: Optional[ProductionPlan] = None
    edit_plan: Optional[EditPlan] = None
    audio_plan: Optional[AudioPlan] = None
    packaging: Optional[VideoPackaging] = None
    qa: Optional[QAResult] = None
    output_video_path: Optional[str] = None
    output_thumbnail_path: Optional[str] = None
    output_subtitles_path: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    stage_durations: Dict[str, float] = Field(default_factory=dict)
