from typing import Optional, Dict, Any, List
from models.base import BaseModel, Field
from models.production import ProductionPlan, ProductionManifest
from models.audio import AudioPlan
from models.metadata import VideoPackaging
from models.qa import QAResult

class FlowState(BaseModel):
    project_id: str
    script: str
    style: str = "Cinematic Documentary"
    voice_name: str = "Kore"
    aspect_ratio: str = "16:9"
    resolution: str = "1080p"
    stage: str = "init"
    plan: Optional[ProductionPlan] = None
    audio_plan: Optional[AudioPlan] = None
    packaging: Optional[VideoPackaging] = None
    qa_result: Optional[QAResult] = None
    video_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    subtitles_path: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    is_completed: bool = False
