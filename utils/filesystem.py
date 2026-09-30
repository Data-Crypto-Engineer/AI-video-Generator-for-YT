import os
import json
import hashlib
from typing import Dict, Any, Optional

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspace"))

class WorkspaceManager:
    """
    Manages deterministic workspace structure:
    workspace/
      <project_id>/
        script.txt
        production.json
        scenes/
          scene_001/
            visual.png
            metadata.json
        audio/
          scene_001.wav
        video/
          final_video.mp4
        thumbnail/
          thumbnail.jpg
        subtitles/
          subtitles.srt
        qa/
          qa_report.json
    """
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_dir = os.path.join(WORKSPACE_ROOT, project_id)
        self.scenes_dir = os.path.join(self.project_dir, "scenes")
        self.audio_dir = os.path.join(self.project_dir, "audio")
        self.video_dir = os.path.join(self.project_dir, "video")
        self.thumbnail_dir = os.path.join(self.project_dir, "thumbnail")
        self.subtitles_dir = os.path.join(self.project_dir, "subtitles")
        self.qa_dir = os.path.join(self.project_dir, "qa")
        self._ensure_dirs()

    def _ensure_dirs(self):
        for directory in [
            self.project_dir,
            self.scenes_dir,
            self.audio_dir,
            self.video_dir,
            self.thumbnail_dir,
            self.subtitles_dir,
            self.qa_dir,
        ]:
            os.makedirs(directory, exist_ok=True)

    def get_scene_dir(self, scene_id: int) -> str:
        s_dir = os.path.join(self.scenes_dir, f"scene_{scene_id:03d}")
        os.makedirs(s_dir, exist_ok=True)
        return s_dir

    def get_scene_visual_path(self, scene_id: int) -> str:
        return os.path.join(self.get_scene_dir(scene_id), "visual.png")

    def get_scene_audio_path(self, scene_id: int) -> str:
        return os.path.join(self.audio_dir, f"scene_{scene_id:03d}.wav")

    def get_final_video_path(self) -> str:
        return os.path.join(self.video_dir, "final_video.mp4")

    def get_thumbnail_path(self) -> str:
        return os.path.join(self.thumbnail_dir, "thumbnail.jpg")

    def get_subtitles_path(self) -> str:
        return os.path.join(self.subtitles_dir, "subtitles.srt")

    def get_manifest_path(self) -> str:
        return os.path.join(self.project_dir, "production_manifest.json")

    def save_manifest(self, manifest_data: Dict[str, Any]):
        with open(self.get_manifest_path(), "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    def load_manifest(self) -> Optional[Dict[str, Any]]:
        path = self.get_manifest_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

def compute_script_hash(script_text: str) -> str:
    return hashlib.sha256(script_text.strip().encode("utf-8")).hexdigest()[:16]
