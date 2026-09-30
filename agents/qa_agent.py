from typing import Optional
from models.production import ProductionPlan
from models.qa import QAResult, QAStatus
from tools.media_validation_tool import MediaValidationTool
from utils.logging import get_logger

logger = get_logger("qa_agent")

class QAAgent:
    def __init__(self, validation_tool: Optional[MediaValidationTool] = None):
        self.validation_tool = validation_tool or MediaValidationTool()

    def audit_production(
        self,
        production_plan: ProductionPlan,
        video_path: str,
        thumbnail_path: Optional[str] = None,
        subtitles_path: Optional[str] = None
    ) -> QAResult:
        logger.info(f"QA Agent initiating forensic QC on {video_path}...")
        result = self.validation_tool.inspect_production(
            production_plan=production_plan,
            video_path=video_path,
            thumbnail_path=thumbnail_path,
            subtitles_path=subtitles_path
        )

        if result.status == QAStatus.PASS:
            logger.info(f"QA Agent: [PASS] Score={result.score}% (All broadcast criteria satisfied).")
        else:
            logger.warning(f"QA Agent: [FAIL] Score={result.score}%, Errors={result.errors}")

        return result
