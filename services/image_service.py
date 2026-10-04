# In generate_scene_visual():
try:
    success, path = self.provider.generate_image(
        prompt=scene.visual_prompt,
        output_path=output_path
    )
    setattr(scene, "visual_source", "Cloudflare FLUX")
    self._save_scene_metadata(workspace, scene, output_path, "Cloudflare FLUX")
    return SceneVisualResult(...)
except Exception as e:
    err_str = str(e)
    if "10,000 neurons" in err_str or "4006" in err_str or "429" in err_str:
        setattr(scene, "quota_exhausted", True)
...
# When fallback completes:
if fallback_ok:
    setattr(scene, "visual_source", source_name)
    self._save_scene_metadata(workspace, scene, fallback_path, source_name)
