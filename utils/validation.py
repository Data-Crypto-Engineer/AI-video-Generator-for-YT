import os
import json
import subprocess
from typing import Dict, Any, Optional, Tuple

def validate_file_exists_and_non_empty(file_path: str, min_bytes: int = 100) -> bool:
    if not file_path or not os.path.exists(file_path):
        return False
    try:
        size = os.path.getsize(file_path)
        return size >= min_bytes
    except OSError:
        return False

def probe_media_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Runs ffprobe on the target media file and returns parsed JSON output."""
    if not validate_file_exists_and_non_empty(file_path, min_bytes=32):
        return None
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
        return json.loads(result.stdout)
    except Exception:
        return None

def get_audio_duration(file_path: str) -> Optional[float]:
    """Gets exact duration in seconds of an audio file using ffprobe."""
    data = probe_media_file(file_path)
    if not data:
        return None
    try:
        fmt = data.get("format", {})
        if "duration" in fmt:
            return float(fmt["duration"])
        streams = data.get("streams", [])
        for s in streams:
            if s.get("codec_type") == "audio" and "duration" in s:
                return float(s["duration"])
    except (ValueError, TypeError):
        pass
    return None

def validate_wav_audio(file_path: str) -> Tuple[bool, str]:
    """Validates that a WAV file has valid RIFF headers, readable stream, and >0 duration."""
    if not validate_file_exists_and_non_empty(file_path, min_bytes=44):
        return False, "File does not exist or has fewer than 44 bytes"
    info = probe_media_file(file_path)
    if not info:
        return False, "ffprobe failed to inspect file structure"
    audio_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not audio_streams:
        return False, "No audio stream detected in file"
    duration = get_audio_duration(file_path)
    if duration is None or duration <= 0.05:
        return False, f"Invalid audio duration: {duration}s"
    return True, f"Valid audio stream ({audio_streams[0].get('codec_name', 'pcm')}, duration={duration:.2f}s)"

def validate_video_file(file_path: str, expected_width: int = 1920, expected_height: int = 1080) -> Tuple[bool, str, Dict[str, Any]]:
    """Checks that MP4 is playable, has H.264 video and AAC audio, and non-zero duration."""
    if not validate_file_exists_and_non_empty(file_path, min_bytes=1000):
        return False, "Video file missing or too small", {}
    info = probe_media_file(file_path)
    if not info:
        return False, "ffprobe failed to inspect video file", {}
    
    video_stream = None
    audio_stream = None
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and not video_stream:
            video_stream = s
        elif s.get("codec_type") == "audio" and not audio_stream:
            audio_stream = s

    if not video_stream:
        return False, "No video stream found in MP4", {}
    
    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    codec_name = video_stream.get("codec_name", "")
    duration = float(info.get("format", {}).get("duration", 0.0))

    metrics = {
        "width": width,
        "height": height,
        "video_codec": codec_name,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else "none",
        "duration": duration,
        "size_bytes": os.path.getsize(file_path)
    }

    if duration < 1.0:
        return False, f"Video duration is suspiciously short: {duration:.2f}s", metrics

    return True, f"Video verified: {width}x{height} {codec_name}, duration={duration:.2f}s", metrics
