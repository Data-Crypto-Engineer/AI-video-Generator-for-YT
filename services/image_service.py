import os
import json
import string
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
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

        # 1. Check existing cached image
        if not force_regenerate and validate_file_exists_and_non_empty(output_path, min_bytes=5000):
            logger.info(f"Reusing cached visual for scene {scene.id:02d}: {output_path}")
            return SceneVisualResult(
                scene_id=scene.id,
                status="completed",
                image_path=output_path,
                prompt_used=scene.visual_prompt
            )

        logger.info(f"Generating visual for scene {scene.id:02d} with Cloudflare: '{scene.visual_prompt[:60]}...'")

        # 2. Try Primary: Cloudflare FLUX
        try:
            success, path = self.provider.generate_image(
                prompt=scene.visual_prompt,
                output_path=output_path
            )
            setattr(scene, "visual_source", "Cloudflare FLUX")
            self._save_scene_metadata(workspace, scene, output_path, "Cloudflare FLUX")
            return SceneVisualResult(
                scene_id=scene.id,
                status="completed",
                image_path=path,
                prompt_used=scene.visual_prompt
            )
        except Exception as e:
            err_str = str(e)
            logger.warning(f"Cloudflare FLUX visual generation failed ({err_str}). Deploying dynamic context search...")
            if "10,000 neurons" in err_str or "4006" in err_str or "429" in err_str:
                setattr(scene, "quota_exhausted", True)

        # 3. Dynamic Context Search Fallback
        fallback_ok, fallback_path, source_name = self._generate_fallback_visual(scene, output_path)
        if fallback_ok:
            setattr(scene, "visual_source", source_name)
            self._save_scene_metadata(workspace, scene, fallback_path, source_name)
            return SceneVisualResult(
                scene_id=scene.id,
                status="completed",
                image_path=fallback_path,
                prompt_used=scene.visual_prompt
            )
        else:
            return SceneVisualResult(
                scene_id=scene.id,
                status="failed",
                image_path=None,
                prompt_used=scene.visual_prompt,
                error="All visual generators exhausted"
            )

    def _save_scene_metadata(self, workspace: WorkspaceManager, scene: Scene, visual_file: str, source: str = "Cloudflare FLUX"):
        try:
            scene_meta_path = os.path.join(workspace.get_scene_dir(scene.id), "metadata.json")
            with open(scene_meta_path, "w", encoding="utf-8") as f:
                json.dump({
                    "scene_id": scene.id,
                    "prompt": scene.visual_prompt,
                    "duration": scene.duration,
                    "camera_motion": scene.camera_motion.value if hasattr(scene.camera_motion, "value") else str(scene.camera_motion),
                    "transition": scene.transition.value if hasattr(scene.transition, "value") else str(scene.transition),
                    "visual_file": visual_file,
                    "visual_source": source
                }, f, indent=2)
        except Exception:
            pass

    def _generate_fallback_visual(self, scene: Scene, output_path: str) -> Tuple[bool, str, str]:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        stopwords = {
            "close-up", "person", "subtle", "glowing", "around", "region", "standing",
            "cinematic", "photorealistic", "ultra", "high", "quality", "with", "from",
            "shot", "scene", "view", "looking", "facing", "background", "foreground"
        }
        words = [w.lower().strip(string.punctuation) for w in scene.visual_prompt.split() if len(w) > 3 and w.lower() not in stopwords]
        keywords = words[:3] if words else ["peaceful", "nature"]
        search_query = " ".join(keywords)

        try:
            wiki_url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={urllib.parse.quote(search_query)}&gsrnamespace=6&format=json&prop=imageinfo&iiprop=url|mime&iiurlwidth=1920"
            req = urllib.request.Request(wiki_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pages = data.get("query", {}).get("pages", {})
                for pid, p in pages.items():
                    info = p.get("imageinfo", [{}])[0]
                    mime = info.get("mime", "")
                    if "image/jpeg" in mime or "image/png" in mime:
                        img_url = info.get("thumburl") or info.get("url")
                        if img_url:
                            dl_req = urllib.request.Request(img_url, headers=headers)
                            with urllib.request.urlopen(dl_req, timeout=12) as dl_resp:
                                img_bytes = dl_resp.read()
                                if len(img_bytes) > 5000:
                                    with open(output_path, "wb") as f:
                                        f.write(img_bytes)
                                    return True, output_path, f"Context Search ({search_query})"
        except Exception:
            pass

        # Backup high-res photography
        backup_url = f"https://picsum.photos/1920/1080?random={scene.id + 10}"
        try:
            req = urllib.request.Request(backup_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = resp.read()
                if len(data) > 5000:
                    with open(output_path, "wb") as f:
                        f.write(data)
                    return True, output_path, "Curated 1080p Library"
        except Exception:
            return False, output_path, "Failed"

        return False, output_path, "Failed"

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
