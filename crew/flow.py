import os
import time
from typing import Optional, Dict, Any, Callable, List
from models.scene import Scene, SceneStatus
from models.production import ProductionPlan, ProductionManifest, EditPlan
from models.audio import AudioPlan
from crew.schemas import FlowState
from crew.crew import VideoProductionCrew
from services.script_service import ScriptNormalizer
from utils.filesystem import WorkspaceManager, compute_script_hash
from utils.logging import get_logger, PipelineLogger
from utils.validation import get_audio_duration

logger = get_logger("production_flow")

# Optional CrewAI Flow imports with graceful fallback
try:
    from crewai.flow.flow import Flow, start, listen
    HAS_CREWAI_FLOW = True
except ImportError:
    HAS_CREWAI_FLOW = False
    class Flow:
        def __init__(self, **kwargs):
            pass
    def start():
        def decorator(f):
            return f
        return decorator
    def listen(*args, **kwargs):
        def decorator(f):
            return f
        return decorator

class VideoProductionFlow(Flow):
    """
    CrewAI Flow-compatible multi-agent production orchestration pipeline.
    Orchestrates the 8 specialized agents and deterministic multimedia engines:
    START -> Script Normalization -> Director -> Voice (TTS) -> Timeline Construction
    -> Visuals -> Music/SFX -> Edit & Assembly -> Subtitles -> QA -> Packaging -> Manifest.
    """
    def __init__(self, project_id: str, progress_callback: Optional[Callable[[str, str, float], None]] = None):
        super().__init__()
        self.project_id = project_id
        self.workspace = WorkspaceManager(project_id)
        self.crew = VideoProductionCrew()
        self.script_normalizer = ScriptNormalizer()
        self.pipe_logger = PipelineLogger(project_id)
        self.progress_callback = progress_callback

    def _notify(self, stage: str, message: str, progress: float):
        self.pipe_logger.log_stage(stage, message)
        if self.progress_callback:
            try:
                self.progress_callback(stage, message, progress)
            except Exception:
                pass

    @start()
    def run_v1_pipeline(
        self,
        script: str,
        style: str = "The Soul Sanctuary (Peaceful & Spiritual)",
        voice_name: str = "Kore",
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
        force_regenerate: bool = False
    ) -> FlowState:
        """
        Executes Version 1 with authoritative audio-first timeline architecture:
        RAW SCRIPT -> NORMALIZER -> DIRECTOR -> VOICE TTS -> TIMELINE CONSTRUCTION
        -> FLUX VISUALS -> MUSIC/SFX -> FFMPEG ASSEMBLY -> SUBTITLES -> PRODUCTION QA -> THUMBNAIL -> MANIFEST
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
            original_script=script,
            errors=[],
            warnings=[]
        )

        try:
            # Stage 1: Script Normalization & Religious Quote Verification
            self._notify("Script", "Normalizing script punctuation, spacing, and verifying source integrity...", 0.05)
            state.stage = "script_normalization"
            normalized_script, script_warnings = self.script_normalizer.normalize(script)
            state.normalized_script = normalized_script
            if script_warnings:
                state.warnings.extend(script_warnings)
                for w in script_warnings:
                    logger.warning(f"Script verification notice: {w}")

            # Stage 2: Director Agent
            self._notify("Director", f"Decomposing script into cinematic scenes (style='{style}', aspect_ratio={aspect_ratio})...", 0.15)
            state.stage = "director"
            state.plan = self.crew.director.create_production_plan(
                script=normalized_script,
                project_id=self.project_id,
                style=style,
                voice_name=voice_name,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                original_script=script,
                script_warnings=script_warnings
            )

            # Stage 3: Voice Agent (Gemini TTS)
            # Narration is generated first so measured audio durations become the authoritative timeline
            self._notify("Voice", f"Synthesizing narration for {len(state.plan.scenes)} scenes with Gemini TTS ({voice_name})...", 0.30)
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

            # Stage 4: Authoritative Timeline Construction
            # Synchronize scene duration strictly to measured audio duration
            self._notify("Timeline", "Constructing authoritative production timeline from measured audio streams...", 0.42)
            state.stage = "timeline"
            current_time = 0.0
            for scene in state.plan.scenes:
                # Measure exact duration using ffprobe
                if scene.audio_path and os.path.exists(scene.audio_path):
                    measured_dur = get_audio_duration(scene.audio_path)
                    if measured_dur and measured_dur > 0.1:
                        scene.audio_duration = round(measured_dur, 2)
                        scene.duration = round(measured_dur, 2)
                
                scene.start_time = round(current_time, 2)
                scene.end_time = round(current_time + scene.duration, 2)
                current_time += scene.duration
                logger.info(f"Timeline Scene {scene.id:02d}: {scene.start_time:.2f}s -> {scene.end_time:.2f}s (dur={scene.duration:.2f}s)")

            state.plan.total_duration = round(current_time, 2)

            # Stage 5: Visual Agent (Cloudflare FLUX Schnell)
            self._notify("Visual", f"Synthesizing {len(state.plan.scenes)} camera visuals with Cloudflare FLUX...", 0.55)
            state.stage = "visuals"
            vis_results = self.crew.visual.generate_all_visuals(
                scenes=state.plan.scenes,
                workspace=self.workspace,
                force_regenerate=force_regenerate
            )
            failed_vis = [r for r in vis_results if r.status != "completed"]
            if failed_vis:
                state.warnings.append(f"{len(failed_vis)} scene visual(s) had generation issues; fallback assets deployed.")

            # Update scene status to COMPLETED if both audio and visual are present
            for scene in state.plan.scenes:
                if scene.audio_path and scene.visual_path and os.path.exists(scene.audio_path) and os.path.exists(scene.visual_path):
                    scene.status = SceneStatus.COMPLETED
                else:
                    scene.status = SceneStatus.PROCESSING

            # Stage 6: Music/SFX Agent
            self._notify("Music/SFX", f"Formulating audio plan and placing SFX cues for mood '{state.plan.music_mood}'...", 0.65)
            state.stage = "audio_plan"
            state.audio_plan = self.crew.music.create_audio_plan(
                scenes=state.plan.scenes,
                music_mood=state.plan.music_mood
            )
            if state.audio_plan.music.status == "skipped":
                state.warnings.append("No verified licensed background music available in local library; continuing without music.")

            # Stage 7: Editor Agent (Deterministic FFmpeg Engine)
            self._notify("Editor", f"Rendering video with Ken Burns motion, ducked music, and subtitles ({aspect_ratio}, {resolution})...", 0.78)
            state.stage = "editor"
            render_ok, video_path, srt_path, edit_plan = self.crew.editor.render_production(
                scenes=state.plan.scenes,
                audio_plan=state.audio_plan,
                workspace=self.workspace,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                burn_subtitles=True
            )
            if not render_ok or not video_path:
                raise RuntimeError(f"FFmpeg assembly failed: {video_path}")
            state.video_path = video_path
            state.subtitles_path = srt_path
            state.edit_plan = edit_plan

            # Stage 8: Thumbnail Agent & YouTube Metadata Packaging
            self._notify("Thumbnail", "Generating high-impact thumbnail and tailored YouTube packaging metadata...", 0.88)
            state.stage = "thumbnail"
            state.packaging = self.crew.thumbnail.package_video(
                production_plan=state.plan,
                workspace=self.workspace
            )
            state.thumbnail_path = state.packaging.thumbnail_path

            # Stage 9: QA Agent (Real Production QC)
            self._notify("QA", "Performing forensic verification of video stream, aspect ratio, codecs, and sync...", 0.95)
            state.stage = "qa"
            state.qa_result = self.crew.qa.audit_production(
                production_plan=state.plan,
                video_path=state.video_path,
                thumbnail_path=state.thumbnail_path,
                subtitles_path=state.subtitles_path
            )

            # Stage 10: Manifest Generation
            self._notify("Manifest", "Writing immutable production manifest...", 0.99)
            qa_val = state.qa_result.status.value if hasattr(state.qa_result.status, "value") else str(state.qa_result.status)
            manifest = ProductionManifest(
                project_id=self.project_id,
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                script_hash=script_hash,
                original_script=state.original_script,
                normalized_script=state.normalized_script,
                status="completed" if qa_val == "PASS" else ("completed_with_warnings" if qa_val == "WARNING" else "failed_qa"),
                stage="completed",
                config=state.plan.project,
                plan=state.plan,
                edit_plan=state.edit_plan,
                audio_plan=state.audio_plan,
                packaging=state.packaging,
                qa=state.qa_result,
                output_video_path=state.video_path,
                output_thumbnail_path=state.thumbnail_path,
                output_subtitles_path=state.subtitles_path,
                errors=list(state.errors or []) + list(state.qa_result.errors or []),
                warnings=list(state.warnings or []) + list(state.qa_result.warnings or []),
                stage_durations={"total_seconds": round(time.time() - start_time, 2)}
            )
            self.workspace.save_manifest(manifest.model_dump())

            state.is_completed = (qa_val != "FAIL")
            state.stage = "completed"
            self._notify("Complete", "Production complete! Video, thumbnail, subtitles, and manifest are ready.", 1.0)
            return state

        except Exception as e:
            logger.error(f"Production pipeline halted: {e}")
            state.errors.append(str(e))
            state.stage = "failed"
            self._notify("Failed", f"Production halted at stage '{state.stage}': {e}", 1.0)
            return state

    @listen("publish_v2")
    def run_v2_publish(
        self,
        privacy_status: str = "private"
    ) -> Dict[str, Any]:
        """
        Executes Version 2: Publishes the V1 finalized assets to YouTube via official OAuth.
        Does NOT simulate when credentials are missing; returns status='not_authenticated'.
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
            hook_concept=t_data.get("hook_concept", "Contemplative focal subject"),
            visual_prompt=t_data.get("visual_prompt", "Prompt"),
            overlay_text=t_data.get("overlay_text", "FIND PEACE")
        )
        m_data = pkg_data.get("metadata", {})
        meta = YouTubeMetadata(
            title=m_data.get("title", "The Soul Sanctuary"),
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

        self._notify("YouTube", f"Contacting YouTube Data API v3 (privacy={privacy_status})...", 0.5)
        result = self.crew.youtube.publish(
            video_path=video_path,
            packaging=packaging,
            privacy_status=privacy_status
        )

        # Update manifest with real YouTube outcome
        manifest_data["youtube"] = {
            "authenticated": result.get("status") != "not_authenticated",
            "video_id": result.get("video_id"),
            "url": result.get("url"),
            "privacy_status": result.get("privacy_status"),
            "upload_status": result.get("status", "unknown"),
            "message": result.get("message")
        }
        if result.get("video_id"):
            manifest_data["packaging"]["published_video_id"] = result.get("video_id")
            manifest_data["packaging"]["published_url"] = result.get("url")

        self.workspace.save_manifest(manifest_data)
        self._notify("YouTube", f"YouTube publish result: {result.get('message')}", 1.0)
        return result
