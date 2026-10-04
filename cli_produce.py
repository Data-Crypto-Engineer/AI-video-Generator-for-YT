import sys
import os
import json
import uuid
from crew.flow import VideoProductionFlow
from utils.filesystem import WorkspaceManager

def main():
    script_text = sys.argv[1] if len(sys.argv) > 1 else (
        "In the darkest trenches of our oceans, life flourishes without sunlight. "
        "Bioluminescent creatures produce living fire, lighting up the abyss."
    )
    style = sys.argv[2] if len(sys.argv) > 2 else "The Soul Sanctuary (Peaceful & Spiritual)"
    voice = sys.argv[3] if len(sys.argv) > 3 else "Kore"
    aspect = sys.argv[4] if len(sys.argv) > 4 else "16:9"
    resolution = sys.argv[5] if len(sys.argv) > 5 else "1080p"

    project_id = str(uuid.uuid4())
    print(f"Starting Video Production Pipeline for Project: {project_id}")
    print(f"Script: {script_text}")
    print(f"Parameters: style='{style}', voice='{voice}', aspect='{aspect}', res='{resolution}'")

    def on_progress(stage, msg, pct):
        print(f"[{int(pct*100)}%] [{stage}] {msg}")

    flow = VideoProductionFlow(project_id, progress_callback=on_progress)
    state = flow.run_v1_pipeline(
        script=script_text,
        style=style,
        voice_name=voice,
        aspect_ratio=aspect,
        resolution=resolution
    )

    if state.is_completed:
        print("\nProduction SUCCESS!")
        print(f"Final MP4 Video: {state.video_path}")
        print(f"Thumbnail: {state.thumbnail_path}")
        print(f"Subtitles: {state.subtitles_path}")
        print(f"QA Score: {state.qa_result.score if state.qa_result else 'N/A'}%")
    else:
        print("\nProduction FAILED!")
        print(f"Errors: {state.errors}")

if __name__ == "__main__":
    main()
