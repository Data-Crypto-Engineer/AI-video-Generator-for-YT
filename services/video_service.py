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
        aspect_ratio: str = "16:9",
        resolution: str = "1080p",
        burn_subtitles: bool = True
    ) -> Tuple[bool, str, Optional[EditPlan]]:
        """
        Executes the deterministic FFmpeg assembly pipeline:
        Visuals + Ken Burns Motion + Narration Audio -> Scene Clips -> Concat with Transitions -> Mixed Audio (Narration + Ducked Music + SFX) -> Subtitles -> Final MP4
        """
        is_portrait = "9:16" in aspect_ratio or aspect_ratio == "portrait"
        if resolution == "1080p":
            width, height = (1080, 1920) if is_portrait else (1920, 1080)
        else: # 720p
            width, height = (720, 1280) if is_portrait else (1280, 720)
        fps = 30

        temp_dir = tempfile.mkdtemp(prefix="video_assemble_")
        scene_clip_paths: List[str] = []
        clip_durations: List[float] = []
        transitions: List[str] = []
        edit_scene_plans: List[EditScenePlan] = []

        try:
            current_time = 0.0

            # Step 1: Build EditPlan and render each scene clip with motion
            for scene in scenes:
                # Authoritative duration from actual audio or measured duration
                dur = scene.audio_duration or scene.duration or 6.0
                motion = scene.camera_motion.value if hasattr(scene.camera_motion, "value") else str(scene.camera_motion)
                trans = scene.transition.value if hasattr(scene.transition, "value") else str(scene.transition)

                clip_out = os.path.join(temp_dir, f"clip_{scene.id:03d}.mp4")

                if not scene.visual_path or not os.path.exists(scene.visual_path):
                    logger.error(f"Cannot render scene {scene.id}: visual file missing ({scene.visual_path})")
                    return False, f"Scene {scene.id} visual missing", None

                if not scene.audio_path or not os.path.exists(scene.audio_path):
                    logger.error(f"Cannot render scene {scene.id}: audio file missing ({scene.audio_path})")
                    return False, f"Scene {scene.id} audio missing", None

                # Record scene in edit plan with authoritative timestamps
                edit_scene_plans.append(EditScenePlan(
                    scene_id=scene.id,
                    start_time=round(current_time, 2),
                    end_time=round(current_time + dur, 2),
                    duration=round(dur, 2),
                    visual_path=scene.visual_path,
                    audio_path=scene.audio_path,
                    motion=motion,
                    transition_in="crossfade" if current_time > 0 and trans == "crossfade" else "cut",
                    transition_out=trans
                ))

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
                    return False, f"Failed rendering scene {scene.id}", None

                scene_clip_paths.append(clip_out)
                clip_durations.append(dur)
                transitions.append(trans)
                current_time += dur

            total_duration = current_time

            # Format SFX cues for edit plan
            sfx_dict_cues = []
            if audio_plan and audio_plan.sfx:
                for cue in audio_plan.sfx:
                    sfx_dict_cues.append({
                        "scene_id": cue.scene_id,
                        "name": cue.name,
                        "file": cue.file,
                        "start_time": cue.start_time,
                        "volume": cue.volume
                    })

            # Create the definitive EditPlan
            edit_plan = EditPlan(
                project_id=workspace.project_id,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                width=width,
                height=height,
                fps=fps,
                scenes=edit_scene_plans,
                audio=audio_plan,
                sfx_cues=sfx_dict_cues,
                music_ducking_enabled=True,
                subtitles_file=subtitles_path,
                output_path=workspace.get_final_video_path()
            )

            # Step 2: Concatenate scene clips with transitions
            raw_concat_video = os.path.join(temp_dir, "raw_concatenated.mp4")
            concat_ok, used_transition = self.ffmpeg.concatenate_with_transitions(
                clip_paths=scene_clip_paths,
                durations=clip_durations,
                transitions=transitions,
                output_path=raw_concat_video
            )
            if not concat_ok or not os.path.exists(raw_concat_video):
                return False, "Failed to concatenate scene video clips", None

            # Step 3: Mix background audio (Narration + Ducked Music + SFX)
            mixed_audio_video = os.path.join(temp_dir, "mixed_audio.mp4")
            music_file = audio_plan.music.file if audio_plan and audio_plan.music and audio_plan.music.status == "selected" else None
            music_vol = audio_plan.music.volume if audio_plan and audio_plan.music else 0.12
            duck_vol = audio_plan.music.duck_volume if audio_plan and audio_plan.music else 0.04
            sfx_list = audio_plan.sfx if audio_plan else []

            mix_ok = self.ffmpeg.mix_audio_timeline(
                video_input=raw_concat_video,
                music_path=music_file,
                sfx_cues=sfx_list,
                output_path=mixed_audio_video,
                total_duration=total_duration,
                narration_vol=1.0,
                music_vol=music_vol,
                duck_vol=duck_vol
            )

            current_video = mixed_audio_video if mix_ok and os.path.exists(mixed_audio_video) else raw_concat_video

            # Step 4: Burn subtitles or copy to final output
            final_output = workspace.get_final_video_path()

            if burn_subtitles and subtitles_path and os.path.exists(subtitles_path):
                burn_ok = self.ffmpeg.burn_subtitles(
                    video_input=current_video,
                    srt_path=subtitles_path,
                    output_path=final_output,
                    aspect_ratio=aspect_ratio,
                    font_size=18 if is_portrait else 22,
                    duration=total_duration
                )
                if not burn_ok or not os.path.exists(final_output):
                    import shutil
                    shutil.copy2(current_video, final_output)
            else:
                import shutil
                shutil.copy2(current_video, final_output)

            logger.info(f"Final MP4 assembly complete: {final_output} ({total_duration:.2f}s, {width}x{height}, {aspect_ratio})")
            return True, final_output, edit_plan

        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
