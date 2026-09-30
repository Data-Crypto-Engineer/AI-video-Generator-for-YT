from enum import Enum
from typing import List, Dict, Any, Optional
from .base import BaseModel, Field

class QAStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"

class QACheckItem(BaseModel):
    category: str = Field(..., description="script | visuals | audio | subtitles | video")
    check_name: str
    passed: bool
    details: str
    is_fatal: bool = True

class QAResult(BaseModel):
    status: QAStatus
    score: float = Field(default=100.0, ge=0.0, le=100.0)
    checks: List[QACheckItem] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    video_metrics: Optional[Dict[str, Any]] = None
    recoverable: bool = True
    suggested_repair_step: Optional[str] = None
