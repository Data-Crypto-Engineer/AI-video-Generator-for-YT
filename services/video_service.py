import os
import tempfile
from typing import List, Optional, Tuple
from models.scene import Scene
from models.audio import AudioPlan
from models.production import EditPlan, EditScenePlan
from tools.ffmpeg_tool import FFmpegTool
from utils.filesystem import WorkspaceManager
from utils.logging import get_logger

logger = get_logger("video_service")

class VideoAssemblyService:
    def __init__(self, ffmpeg_tool: Optional[FFmpegTool] = None):
        self.ffmpeg = ffmpeg_tool or FFmpegTool()

    def assemble_final_video(
        self,
        scenes: List[Scene],
        audio_plan: AudioPlan,
        subtitles_path: Optional[str],
        workspace: WorkspaceManager,
        resolution: str = "1080p",
        burn_subtitles: bool = True
    ) -> Tuple[bool, str]:
        """
        Executes the deterministic FFmpeg assembly pipeline:
        Visuals + Ken Burns Motion + Narration Audio -> Scene Clips -> Concat -> Music Mix/Ducking -> Burn Subtitles -> Final MP4
        """
        width = 1920 if resolution == "1080p" else 1280
        height = 1080 if resolution == "1080p" else 720
        fps = 30

        temp_dir = tempfile.mkdtemp(prefix="video_assemble_")
        scene_clip_paths: List[str] = []

        try:
            total_duration = 0.0

            # Step 1: Render each scene clip with motion
            for scene in scenes:
                dur = scene.audio_duration or scene.duration or 6.0
                total_duration += dur

                motion = scene.camera_motion.value if hasattr(scene.camera_motion, "value") else str(scene.camera_motion)
                clip_out = os.path.join(temp_dir, f"clip_{scene.id:03d}.mp4")

                if not scene.visual_path or not os.path.exists(scene.visual_path):
                    logger.error(f"Cannot render scene {scene.id}: visual file missing ({scene.visual_path})")
                    return False, f"Scene {scene.id} visual missing"

                if not scene.audio_path or not os.path.exists(scene.audio_path):
                    logger.error(f"Cannot render scene {scene.id}: audio file missing ({scene.audio_path})")
                    return False, f"Scene {scene.id} audio missing"

                success = self.ffmpeg.render_scene_clip(
                    image_path=scene.visual_path,
                    audio_path=scene.audio_path,
                    output_clip_path=clip_out,
                    duration=dur,
                    motion=motion,
                    width=width,
                    height=height,
                    fps=fps
                )

                if not success or not os.path.exists(clip_out):
                    logger.error(f"Failed to render clip for scene {scene.id}")
                    return False, f"Failed rendering scene {scene.id}"

                scene_clip_paths.append(clip_out)

            # Step 2: Concatenate scene clips
            raw_concat_video = os.path.join(temp_dir, "raw_concatenated.mp4")
            concat_ok = self.ffmpeg.concatenate_scene_clips(scene_clip_paths, raw_concat_video)
            if not concat_ok or not os.path.exists(raw_concat_video):
                return False, "Failed to concatenate scene video clips"

            # Step 3: Mix background music with ducking
            mixed_audio_video = os.path.join(temp_dir, "mixed_audio.mp4")
            music_file = audio_plan.music.file if audio_plan.music and audio_plan.music.status == "selected" else None
            music_vol = audio_plan.music.volume if audio_plan.music else 0.09

            mix_ok = self.ffmpeg.mix_background_audio(
                video_input=raw_concat_video,
                music_path=music_file,
                output_path=mixed_audio_video,
                total_duration=total_duration,
                music_vol=music_vol
            )

            current_video = mixed_audio_video if mix_ok and os.path.exists(mixed_audio_video) else raw_concat_video

            # Step 4: Burn subtitles or copy to final output
            final_output = workspace.get_final_video_path()

            if burn_subtitles and subtitles_path and os.path.exists(subtitles_path):
                burn_ok = self.ffmpeg.burn_subtitles(
                    video_input=current_video,
                    srt_path=subtitles_path,
                    output_path=final_output,
                    font_size=21 if resolution == "1080p" else 15
                )
                if not burn_ok or not os.path.exists(final_output):
                    # Fallback copy
                    import shutil
                    shutil.copy2(current_video, final_output)
            else:
                import shutil
                shutil.copy2(current_video, final_output)

            logger.info(f"Final MP4 assembly complete: {final_output} ({total_duration:.2f}s, {resolution})")
            return True, final_output

        finally:
            # Clean temporary clips
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
