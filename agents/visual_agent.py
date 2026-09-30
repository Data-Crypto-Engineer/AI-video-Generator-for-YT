from typing import List, Optional
from models.scene import Scene, SceneVisualResult
from services.image_service import ImageService
from utils.filesystem import WorkspaceManager
from utils.logging import get_logger

logger = get_logger("visual_agent")

class VisualAgent:
    def __init__(self, image_service: Optional[ImageService] = None):
        self.image_service = image_service or ImageService()

    def generate_all_visuals(
        self,
        scenes: List[Scene],
        workspace: WorkspaceManager,
        force_regenerate: bool = False
    ) -> List[SceneVisualResult]:
        logger.info(f"Visual Agent generating images for {len(scenes)} scenes via Cloudflare FLUX...")
        results = self.image_service.generate_all_visuals(scenes, workspace, force_regenerate=force_regenerate)
        successful = sum(1 for r in results if r.status == "completed")
        logger.info(f"Visual Agent completed: {successful}/{len(scenes)} scene visuals ready.")
        return results

    def retry_scene_visual(
        self,
        scene: Scene,
        workspace: WorkspaceManager
    ) -> SceneVisualResult:
        logger.info(f"Visual Agent retrying visual for scene {scene.id}...")
        return self.image_service.generate_scene_visual(scene, workspace, force_regenerate=True)
