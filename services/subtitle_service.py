import os
from typing import List, Tuple
from models.scene import Scene
from utils.logging import get_logger

logger = get_logger("subtitle_service")

def format_timestamp(seconds: float) -> str:
    """Formats float seconds into SRT timestamp HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

class SubtitleService:
    """
    Generates broadcast-grade SRT subtitles synchronized to scene narration and audio timings.
    """
    def generate_srt(self, scenes: List[Scene], output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        srt_lines = []
        entry_idx = 1
        current_time = 0.0

        for scene in scenes:
            duration = scene.audio_duration or scene.duration or 6.0
            narration = scene.narration.strip()

            # Split narration into concise readable subtitle chunks (approx 6-10 words per line)
            words = narration.split()
            if not words:
                current_time += duration
                continue

            # Determine chunk size based on duration and word count
            words_per_sec = max(1.5, len(words) / max(1.0, duration))
            chunk_word_count = 7
            chunks = []
            for i in range(0, len(words), chunk_word_count):
                chunks.append(" ".join(words[i:i + chunk_word_count]))

            chunk_duration = duration / len(chunks)

            for i, chunk in enumerate(chunks):
                start = current_time + (i * chunk_duration)
                end = min(current_time + duration, start + chunk_duration)
                
                srt_lines.append(f"{entry_idx}")
                srt_lines.append(f"{format_timestamp(start)} --> {format_timestamp(end)}")
                srt_lines.append(chunk)
                srt_lines.append("")
                entry_idx += 1

            current_time += duration

        srt_content = "\n".join(srt_lines)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        logger.info(f"Generated SRT subtitles: {output_path} ({entry_idx - 1} entries)")
        return output_path
