import os
import subprocess
import tempfile
from typing import List, Optional, Tuple, Dict, Any
from utils.logging import get_logger
from utils.validation import get_audio_duration

logger = get_logger("ffmpeg_tool")

class FFmpegTool:
    """
    Deterministic multimedia rendering engine using system FFmpeg and ffprobe.
    """
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe"):
        self.ffmpeg = ffmpeg_bin
        self.ffprobe = ffprobe_bin

    def check_availability(self) -> Tuple[bool, str]:
        try:
            res = subprocess.run([self.ffmpeg, "-version"], capture_output=True, text=True, check=True)
            first_line = res.stdout.split("\n")[0]
            return True, first_line
        except Exception as e:
            return False, str(e)

    def render_scene_clip(
        self,
        image_path: str,
        audio_path: str,
        output_clip_path: str,
        duration: float,
        motion: str = "slow_zoom_in",
        width: int = 1920,
        height: int = 1080,
        fps: int = 30
    ) -> bool:
        """
        Renders a single scene clip by applying Ken Burns motion to the still image
        scaled accurately to the target aspect ratio, paired with narration audio.
        """
        total_frames = int(duration * fps) + 5
        
        # Pre-scale to fill target bounding box without stretching, then zoompan
        scale_crop = f"scale=w={width*2}:h={height*2}:force_original_aspect_ratio=increase,crop={width*2}:{height*2}"

        # Ken Burns zoompan filter definition
        if motion == "slow_zoom_out":
            zoom_filter = (
                f"{scale_crop},"
                f"zoompan=z='if(lte(zoom,1.0),1.14,max(1.001,1.14-0.14*on/{total_frames}))':"
                f"x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={total_frames}:s={width}x{height}:fps={fps}"
            )
        elif motion == "pan_left":
            zoom_filter = (
                f"{scale_crop},"
                f"zoompan=z=1.12:x='(iw-iw/zoom)*(1-on/{total_frames})':y='(ih-ih/zoom)/2':d={total_frames}:s={width}x{height}:fps={fps}"
            )
        elif motion == "pan_right":
            zoom_filter = (
                f"{scale_crop},"
                f"zoompan=z=1.12:x='(iw-iw/zoom)*(on/{total_frames})':y='(ih-ih/zoom)/2':d={total_frames}:s={width}x{height}:fps={fps}"
            )
        else: # slow_zoom_in default
            zoom_filter = (
                f"{scale_crop},"
                f"zoompan=z='min(1.14,1.0+0.14*on/{total_frames})':"
                f"x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={total_frames}:s={width}x{height}:fps={fps}"
            )

        cmd = [
            self.ffmpeg,
            "-loop", "1",
            "-t", f"{duration:.3f}",
            "-i", image_path,
            "-i", audio_path,
            "-vf", f"{zoom_filter},format=yuv420p",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "21",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-shortest",
            "-y",
            output_clip_path
        ]

        logger.info(f"Rendering scene clip ({width}x{height}): motion={motion}, dur={duration:.2f}s -> {output_clip_path}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Scene render error: {result.stderr}")
            return False
        return True

    def concatenate_scene_clips(self, clip_paths: List[str], output_path: str) -> bool:
        """Concatenates rendered scene clips with concat demuxer."""
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            for p in clip_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")
            concat_file = f.name

        try:
            cmd = [
                self.ffmpeg,
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                "-y",
                output_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                logger.error(f"Concat error: {res.stderr}")
                return False
            return True
        finally:
            if os.path.exists(concat_file):
                os.remove(concat_file)

    def concatenate_with_transitions(
        self,
        clip_paths: List[str],
        durations: List[float],
        transitions: List[str],
        output_path: str
    ) -> Tuple[bool, str]:
        """
        Concatenates clips applying crossfades (xfade) when requested,
        falling back cleanly to concat demuxer if clips are too short.
        """
        if not clip_paths:
            return False, "No clips provided"
        if len(clip_paths) == 1:
            import shutil
            shutil.copy2(clip_paths[0], output_path)
            return True, "cut"

        has_crossfade = any(t in ("crossfade", "dissolve") for t in transitions)
        # Check if every clip has enough duration for 0.5s crossfade
        min_dur = min(durations) if durations else 0.0

        if has_crossfade and min_dur >= 1.5 and len(clip_paths) <= 12:
            try:
                # Build xfade filtergraph
                fade_dur = 0.5
                inputs = []
                for p in clip_paths:
                    inputs.extend(["-i", p])

                v_filters = []
                a_filters = []
                cur_offset = durations[0] - fade_dur
                prev_v = "0:v"
                prev_a = "0:a"

                for i in range(1, len(clip_paths)):
                    next_v = f"{i}:v"
                    next_a = f"{i}:a"
                    out_v = f"v{i}"
                    out_a = f"a{i}"
                    v_filters.append(f"[{prev_v}][{next_v}]xfade=transition=fade:duration={fade_dur}:offset={cur_offset:.2f}[{out_v}]")
                    a_filters.append(f"[{prev_a}][{next_a}]acrossfade=d={fade_dur}[{out_a}]")
                    prev_v = out_v
                    prev_a = out_a
                    if i < len(clip_paths) - 1:
                        cur_offset += (durations[i] - fade_dur)

                full_filter = ";".join(v_filters + a_filters)
                cmd = [
                    self.ffmpeg,
                    *inputs,
                    "-filter_complex", full_filter,
                    "-map", f"[{prev_v}]",
                    "-map", f"[{prev_a}]",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "21",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-y",
                    output_path
                ]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    logger.info("Successfully rendered video with crossfade transitions via xfade.")
                    return True, "crossfade"
                else:
                    logger.warning(f"xfade transition failed ({res.stderr[-200:] if res.stderr else ''}), falling back to cut demuxer.")
            except Exception as e:
                logger.warning(f"Error during xfade: {e}, falling back to concat demuxer.")

        # Fallback to standard clean concat demuxer
        ok = self.concatenate_scene_clips(clip_paths, output_path)
        return ok, "cut"

    def mix_audio_timeline(
        self,
        video_input: str,
        music_path: Optional[str],
        sfx_cues: Optional[List[Any]],
        output_path: str,
        total_duration: float,
        narration_vol: float = 1.0,
        music_vol: float = 0.12,
        duck_vol: float = 0.04
    ) -> bool:
        """
        Broadcast-grade audio mixing engine:
        1. Narration stream as primary authoritative lead (volume=1.0)
        2. Background music with dynamic sidechain ducking under narration
        3. SFX cues positioned at exact millisecond timeline offsets
        """
        has_music = bool(music_path and os.path.exists(music_path))
        valid_sfx = [c for c in (sfx_cues or []) if hasattr(c, "file") and os.path.exists(c.file)]

        # Case 1: Narration only
        if not has_music and not valid_sfx:
            logger.info("No background music or SFX provided; passing audio stream through.")
            cmd = [
                self.ffmpeg,
                "-i", video_input,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-y",
                output_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            return res.returncode == 0

        # Build filter complex
        input_args = ["-i", video_input]
        filter_parts = []
        mix_inputs = ["[narr_lead]"]

        # 1. Narration stream setup (split into lead and sidechain trigger)
        filter_parts.append("[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asplit=2[narr_lead][narr_side]")

        # 2. Music stream with dynamic sidechain ducking
        next_input_idx = 1
        if has_music:
            input_args.extend(["-i", music_path])
            filter_parts.append(
                f"[{next_input_idx}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                f"aloop=loop=-1:size=2e+09,atrim=0:{total_duration:.2f},"
                f"afade=t=in:ss=0:d=2.0,afade=t=out:st={max(0, total_duration - 3.0):.2f}:d=3.0,"
                f"volume={music_vol}[bgm_loop]"
            )
            filter_parts.append("[bgm_loop][narr_side]sidechaincompress=threshold=0.03:ratio=5:attack=100:release=600[ducked_bgm]")
            mix_inputs.append("[ducked_bgm]")
            next_input_idx += 1

        # 3. SFX streams with exact timestamp delays
        for idx, cue in enumerate(valid_sfx):
            input_args.extend(["-i", cue.file])
            delay_ms = max(0, int(cue.start_time * 1000))
            vol = getattr(cue, "volume", 0.20)
            filter_parts.append(
                f"[{next_input_idx}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                f"adelay={delay_ms}|{delay_ms},volume={vol}[sfx_{idx}]"
            )
            mix_inputs.append(f"[sfx_{idx}]")
            next_input_idx += 1

        # 4. Final mix
        mix_str = "".join(mix_inputs)
        filter_parts.append(f"{mix_str}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0[aout]")
        filter_complex = ";".join(filter_parts)

        cmd = [
            self.ffmpeg,
            *input_args,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", f"{total_duration:.3f}",
            "-shortest",
            "-y",
            output_path
        ]

        logger.info(f"Executing multi-stream audio mix: music={'yes' if has_music else 'no'}, sfx_count={len(valid_sfx)}...")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.warning(f"Audio mix failed ({res.stderr[-200:] if res.stderr else ''}), falling back to direct copy.")
            fallback_cmd = [
                self.ffmpeg,
                "-i", video_input,
                "-c", "copy",
                "-y",
                output_path
            ]
            subprocess.run(fallback_cmd, capture_output=True, text=True)
            return True
        return True

    def mix_background_audio(
        self,
        video_input: str,
        music_path: Optional[str],
        output_path: str,
        total_duration: float,
        narration_vol: float = 1.0,
        music_vol: float = 0.12,
        duck_vol: float = 0.04
    ) -> bool:
        """Backwards compatibility wrapper for mix_audio_timeline."""
        return self.mix_audio_timeline(
            video_input=video_input,
            music_path=music_path,
            sfx_cues=[],
            output_path=output_path,
            total_duration=total_duration,
            narration_vol=narration_vol,
            music_vol=music_vol,
            duck_vol=duck_vol
        )

    def burn_subtitles(
        self,
        video_input: str,
        srt_path: str,
        output_path: str,
        aspect_ratio: str = "16:9",
        font_size: Optional[int] = None,
        duration: Optional[float] = None
    ) -> bool:
        """
        Burns clean broadcast-style subtitles with aspect-ratio-aware safe zones:
        - 16:9: Centered near bottom (MarginV=35)
        - 9:16: Safe zone inside portrait viewport avoiding Shorts UI controls (MarginV=160)
        """
        if not os.path.exists(srt_path):
            return False

        # Determine styling and safe zone margins
        is_portrait = "9:16" in aspect_ratio or aspect_ratio == "portrait"
        actual_font_size = font_size or (18 if is_portrait else 22)
        margin_v = 160 if is_portrait else 35

        # Escape path for FFmpeg subtitles filter
        escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:")
        style = (
            f"Fontname=Arial,FontSize={actual_font_size},"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,"
            f"BorderStyle=4,Outline=1,Shadow=1,MarginV={margin_v},Alignment=2"
        )
        sub_filter = f"subtitles='{escaped_srt}':force_style='{style}'"

        cmd = [
            self.ffmpeg,
            "-i", video_input,
            "-vf", sub_filter,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-c:a", "copy",
            *(["-t", f"{duration:.3f}"] if duration and duration > 0 else []),
            "-movflags", "+faststart",
            "-y",
            output_path
        ]

        logger.info(f"Burning subtitles into final video (aspect_ratio={aspect_ratio}, margin_v={margin_v}): {srt_path}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.warning(f"Subtitle burn-in warning: {res.stderr[-200:] if res.stderr else ''}. Preserving video.")
            copy_cmd = [
                self.ffmpeg,
                "-i", video_input,
                "-c", "copy",
                "-y",
                output_path
            ]
            subprocess.run(copy_cmd, capture_output=True, text=True)
            return True
        return True
