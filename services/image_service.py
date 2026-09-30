import os
import json
from typing import List, Dict, Any, Optional
from models.scene import Scene, SceneVisualResult
from tools.cloudflare_image_tool import ImageProvider, CloudflareFluxProvider
from utils.filesystem import WorkspaceManager
from utils.logging import get_logger
from utils.validation import validate_file_exists_and_non_empty

logger = get_logger("image_service")

class ImageService:
    def __init__(self, provider: Optional[ImageProvider] = None):
        self.provider = provider or CloudflareFluxProvider()

    def generate_scene_visual(
        self,
        scene: Scene,
        workspace: WorkspaceManager,
        force_regenerate: bool = False
    ) -> SceneVisualResult:
        output_path = workspace.get_scene_visual_path(scene.id)

        # Check existing cached image
        if not force_regenerate and validate_file_exists_and_non_empty(output_path, min_bytes=1000):
            logger.info(f"Reusing cached visual for scene {scene.id:02d}: {output_path}")
            return SceneVisualResult(
                scene_id=scene.id,
                status="completed",
                image_path=output_path,
                prompt_used=scene.visual_prompt
            )

        logger.info(f"Generating visual for scene {scene.id:02d} with Cloudflare FLUX: '{scene.visual_prompt[:60]}...'")
        try:
            success, path = self.provider.generate_image(
                prompt=scene.visual_prompt,
                output_path=output_path
            )

            # Write scene metadata
            scene_meta_path = os.path.join(workspace.get_scene_dir(scene.id), "metadata.json")
            with open(scene_meta_path, "w", encoding="utf-8") as f:
                json.dump({
                    "scene_id": scene.id,
                    "prompt": scene.visual_prompt,
                    "duration": scene.duration,
                    "camera_motion": scene.camera_motion.value if hasattr(scene.camera_motion, "value") else str(scene.camera_motion),
                    "transition": scene.transition.value if hasattr(scene.transition, "value") else str(scene.transition),
                    "visual_file": output_path
                }, f, indent=2)

            return SceneVisualResult(
                scene_id=scene.id,
                status="completed",
                image_path=path,
                prompt_used=scene.visual_prompt
            )
        except Exception as e:
            logger.error(f"Visual generation failed for scene {scene.id:02d}: {e}")
            return SceneVisualResult(
                scene_id=scene.id,
                status="failed",
                image_path=None,
                prompt_used=scene.visual_prompt,
                error=str(e)
            )

    def generate_all_visuals(
        self,
        scenes: List[Scene],
        workspace: WorkspaceManager,
        force_regenerate: bool = False
    ) -> List[SceneVisualResult]:
        results = []
        for scene in scenes:
            res = self.generate_scene_visual(scene, workspace, force_regenerate=force_regenerate)
            if res.status == "completed" and res.image_path:
                scene.visual_path = res.image_path
            results.append(res)
        return results
