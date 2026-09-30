import os
import time
from typing import Optional, Dict, Any, Callable
from models.production import ProductionPlan, ProductionManifest
from crew.schemas import FlowState
from crew.crew import VideoProductionCrew
from utils.filesystem import WorkspaceManager, compute_script_hash
from utils.logging import get_logger, PipelineLogger

logger = get_logger("production_flow")

class VideoProductionFlow:
    """
    Deterministic Production Flow orchestrating the 8 specialized agents
    and multimedia services from Script to Final MP4 (V1) and YouTube (V2).
    """
    def __init__(self, project_id: str, progress_callback: Optional[Callable[[str, str, float], None]] = None):
        self.project_id = project_id
        self.workspace = WorkspaceManager(project_id)
        self.crew = VideoProductionCrew()
        self.pipe_logger = PipelineLogger(project_id)
        self.progress_callback = progress_callback

    def _notify(self, stage: str, message: str, progress: float):
        self.pipe_logger.log_stage(stage, message)
        if self.progress_callback:
            try:
                self.progress_callback(stage, message, progress)
            except Exception:
                pass

    def run_v1_pipeline(
        self,
        script: str,
        style: str = "Cinematic Documentary",
        voice_name: str = "Kore",
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
        force_regenerate: bool = False
    ) -> FlowState:
        """
        Executes Version 1: SCRIPT -> SCENES -> VISUALS + VOICE + MUSIC -> FFMPEG -> SUBTITLES -> QA -> THUMBNAIL -> FINAL MP4
        """
        script_hash = compute_script_hash(script)
        start_time = time.time()

        state = FlowState(
            project_id=self.project_id,
            script=script,
            style=style,
            voice_name=voice_name,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            stage="starting",
            errors=[],
            warnings=[]
        )

        try:
            # Stage 1: Director Agent
            self._notify("Director", "Analyzing script and generating scene breakdown...", 0.10)
            state.stage = "director"
            state.plan = self.crew.director.create_production_plan(
                script=script,
                project_id=self.project_id,
                style=style,
                voice_name=voice_name,
                aspect_ratio=aspect_ratio,
                resolution=resolution
            )

            # Stage 2: Visual Agent (Cloudflare FLUX)
            self._notify("Visual", f"Synthesizing {len(state.plan.scenes)} scene visuals with Cloudflare FLUX...", 0.25)
            state.stage = "visuals"
            vis_results = self.crew.visual.generate_all_visuals(
                scenes=state.plan.scenes,
                workspace=self.workspace,
                force_regenerate=force_regenerate
            )
            failed_vis = [r for r in vis_results if r.status != "completed"]
            if failed_vis:
                state.warnings.append(f"{len(failed_vis)} scene visual(s) had generation issues")

            # Stage 3: Voice Agent (Gemini TTS)
            self._notify("Voice", f"Synthesizing narration for {len(state.plan.scenes)} scenes with Gemini TTS ({voice_name})...", 0.45)
            state.stage = "voice"
            audio_results = self.crew.voice.generate_all_narrations(
                scenes=state.plan.scenes,
                workspace=self.workspace,
                voice_name=voice_name,
                force_regenerate=force_regenerate
            )
            failed_audio = [r for r in audio_results if r.status != "completed"]
            if failed_audio:
                raise RuntimeError(f"Narration generation failed for {len(failed_audio)} scene(s)")

            # Stage 4: Music/SFX Agent
            self._notify("Music/SFX", f"Formulating audio plan and calculating ducking curves for mood '{state.plan.music_mood}'...", 0.60)
            state.stage = "audio_plan"
            state.audio_plan = self.crew.music.create_audio_plan(
                scenes=state.plan.scenes,
                music_mood=state.plan.music_mood
            )

            # Stage 5: Editor Agent (FFmpeg deterministic assembly)
            self._notify("Editor", f"Rendering video with Ken Burns motion, ducked music, and subtitles ({resolution})...", 0.75)
            state.stage = "editor"
            render_ok, video_path, srt_path = self.crew.editor.render_production(
                scenes=state.plan.scenes,
                audio_plan=state.audio_plan,
                workspace=self.workspace,
                resolution=resolution,
                burn_subtitles=True
            )
            if not render_ok:
                raise RuntimeError(f"FFmpeg assembly failed: {video_path}")
            state.video_path = video_path
            state.subtitles_path = srt_path

            # Stage 6: Thumbnail Agent
            self._notify("Thumbnail", "Generating high-CTR thumbnail and YouTube packaging metadata...", 0.88)
            state.stage = "thumbnail"
            state.packaging = self.crew.thumbnail.package_video(
                production_plan=state.plan,
                workspace=self.workspace
            )
            state.thumbnail_path = state.packaging.thumbnail_path

            # Stage 7: QA Agent
            self._notify("QA", "Performing forensic verification of video stream and audio metrics with ffprobe...", 0.95)
            state.stage = "qa"
            state.qa_result = self.crew.qa.audit_production(
                production_plan=state.plan,
                video_path=state.video_path,
                thumbnail_path=state.thumbnail_path,
                subtitles_path=state.subtitles_path
            )

            # Stage 8: Manifest Generation
            self._notify("Manifest", "Writing immutable production manifest...", 0.99)
            qa_val = state.qa_result.status.value if hasattr(state.qa_result.status, "value") else str(state.qa_result.status)
            manifest = ProductionManifest(
                project_id=self.project_id,
                script_hash=script_hash,
                status="completed" if qa_val == "PASS" else "completed_with_warnings",
                stage="completed",
                config=state.plan.project,
                plan=state.plan,
                audio_plan=state.audio_plan,
                packaging=state.packaging,
                qa=state.qa_result,
                output_video_path=state.video_path,
                output_thumbnail_path=state.thumbnail_path,
                output_subtitles_path=state.subtitles_path,
                errors=list(state.errors or []),
                warnings=list(state.warnings or []),
                stage_durations={"total_seconds": round(time.time() - start_time, 2)}
            )
            self.workspace.save_manifest(manifest.model_dump())

            state.is_completed = True
            state.stage = "completed"
            self._notify("Complete", "Production complete! Video, thumbnail, subtitles, and manifest are ready.", 1.0)
            return state

        except Exception as e:
            logger.error(f"Production pipeline halted: {e}")
            state.errors.append(str(e))
            state.stage = "failed"
            self._notify("Failed", f"Production halted at stage '{state.stage}': {e}", 1.0)
            return state

    def run_v2_publish(
        self,
        privacy_status: str = "private"
    ) -> Dict[str, Any]:
        """
        Executes Version 2: Publishes the V1 finalized assets to YouTube.
        Reuses the exact same production workspace and packaging.
        """
        manifest_data = self.workspace.load_manifest()
        if not manifest_data:
            raise RuntimeError("Cannot publish to YouTube: No production manifest found. Run V1 production first.")

        video_path = manifest_data.get("output_video_path")
        if not video_path or not os.path.exists(video_path):
            raise RuntimeError(f"Video file missing: {video_path}")

        pkg_data = manifest_data.get("packaging", {})
        from models.metadata import VideoPackaging, ThumbnailConcept, YouTubeMetadata

        t_data = pkg_data.get("thumbnail_concept", {})
        concept = ThumbnailConcept(
            hook_concept=t_data.get("hook_concept", "Hook"),
            visual_prompt=t_data.get("visual_prompt", "Prompt"),
            overlay_text=t_data.get("overlay_text", "WATCH NOW")
        )
        m_data = pkg_data.get("metadata", {})
        meta = YouTubeMetadata(
            title=m_data.get("title", "Cinematic Video"),
            description=m_data.get("description", ""),
            tags=m_data.get("tags", []),
            category_id=m_data.get("category_id", "27"),
            privacy_status=privacy_status
        )
        packaging = VideoPackaging(
            thumbnail_concept=concept,
            thumbnail_path=pkg_data.get("thumbnail_path"),
            metadata=meta
        )

        self._notify("YouTube", f"Uploading MP4 and custom thumbnail to YouTube (privacy={privacy_status})...", 0.5)
        result = self.crew.youtube.publish(
            video_path=video_path,
            packaging=packaging,
            privacy_status=privacy_status
        )

        # Update manifest
        manifest_data["packaging"]["published_video_id"] = result.get("video_id")
        manifest_data["packaging"]["published_url"] = result.get("url")
        self.workspace.save_manifest(manifest_data)

        self._notify("YouTube", f"Publish status: {result.get('message')}", 1.0)
        return result
