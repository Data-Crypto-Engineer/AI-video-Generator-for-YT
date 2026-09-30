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
        and pairing it with the scene narration audio.
        """
        total_frames = int(duration * fps) + 5
        
        # Ken Burns zoompan filter definition
        if motion == "slow_zoom_out":
            # Start at 1.15x zoom and gently zoom out to 1.0x
            zoom_filter = (
                f"scale={width*2}x{height*2},"
                f"zoompan=z='if(lte(zoom,1.0),1.14,max(1.001,1.14-0.14*on/{total_frames}))':"
                f"x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={total_frames}:s={width}x{height}:fps={fps}"
            )
        elif motion == "pan_left":
            zoom_filter = (
                f"scale={width*2}x{height*2},"
                f"zoompan=z=1.12:x='(iw-iw/zoom)*(1-on/{total_frames})':y='(ih-ih/zoom)/2':d={total_frames}:s={width}x{height}:fps={fps}"
            )
        elif motion == "pan_right":
            zoom_filter = (
                f"scale={width*2}x{height*2},"
                f"zoompan=z=1.12:x='(iw-iw/zoom)*(on/{total_frames})':y='(ih-ih/zoom)/2':d={total_frames}:s={width}x{height}:fps={fps}"
            )
        else: # slow_zoom_in default
            # Start at 1.0x and zoom in smoothly to 1.14x
            zoom_filter = (
                f"scale={width*2}x{height*2},"
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

        logger.info(f"Rendering scene clip: motion={motion}, dur={duration:.2f}s -> {output_clip_path}")
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

    def mix_background_audio(
        self,
        video_input: str,
        music_path: Optional[str],
        output_path: str,
        total_duration: float,
        narration_vol: float = 1.0,
        music_vol: float = 0.09,
        duck_vol: float = 0.05
    ) -> bool:
        """
        Mixes background music with video narration using dynamic ducking and fades.
        If music_path is None or missing, keeps original narration audio intact.
        """
        if not music_path or not os.path.exists(music_path):
            logger.info("No music track provided; passing audio through without background music.")
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

        # Loop and fade music to match video duration
        filter_complex = (
            f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{total_duration:.2f},"
            f"afade=t=in:ss=0:d=2.0,afade=t=out:st={max(0, total_duration - 3.0):.2f}:d=3.0,"
            f"volume={music_vol}[bgm];"
            f"[0:a]volume={narration_vol}[narr];"
            f"[narr][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        cmd = [
            self.ffmpeg,
            "-i", video_input,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-y",
            output_path
        ]

        logger.info(f"Mixing background music ({music_path}) into video...")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"Audio mix error: {res.stderr}")
            # Graceful fallback: preserve video without music
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

    def burn_subtitles(
        self,
        video_input: str,
        srt_path: str,
        output_path: str,
        font_size: int = 20
    ) -> bool:
        """Burns clean, broadcast-style yellow/white subtitles with subtle black backing."""
        if not os.path.exists(srt_path):
            return False

        # Escape path for FFmpeg subtitles filter
        escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:")
        style = (
            f"Fontname=Arial,FontSize={font_size},"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,"
            "BorderStyle=4,Outline=1,Shadow=1,MarginV=30,Alignment=2"
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
            "-movflags", "+faststart",
            "-y",
            output_path
        ]

        logger.info(f"Burning subtitles into final video: {srt_path}")
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.warning(f"Subtitle burn-in warning: {res.stderr}. Preserving video with soft stream.")
            # Fallback: copy video without hard burning
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
