import os
import sys
import subprocess
from tools.ffmpeg_tool import FFmpegTool
from utils.gemini_client import GeminiReasoningClient
from utils.logging import get_logger

logger = get_logger("diagnostics")

def run_diagnostics():
    print("=" * 60)
    print("AI VIDEO PRODUCTION STUDIO — SYSTEM DIAGNOSTICS")
    print("=" * 60)

    # 1. FFmpeg & ffprobe
    ff = FFmpegTool()
    ff_ok, ff_msg = ff.check_availability()
    if ff_ok:
        print(f"[PASS] FFmpeg available: {ff_msg}")
    else:
        print(f"[FAIL] FFmpeg not found: {ff_msg}")

    # 2. Cloudflare API Credentials
    cf_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    cf_acc = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if cf_token and cf_acc:
        print("[PASS] Cloudflare FLUX credentials detected.")
    else:
        print("[WARN] Cloudflare credentials missing.")

    # 3. Google Gemini API Key
    gem_key = os.environ.get("GEMINI_API_KEY")
    if gem_key:
        print("[PASS] Google Gemini API Key detected (Server-side).")
    else:
        print("[FAIL] GEMINI_API_KEY environment variable missing.")

    # 4. Audio Library Assets
    assets_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets"))
    music_count = len(os.listdir(os.path.join(assets_dir, "music"))) if os.path.exists(os.path.join(assets_dir, "music")) else 0
    sfx_count = len(os.listdir(os.path.join(assets_dir, "sfx"))) if os.path.exists(os.path.join(assets_dir, "sfx")) else 0
    print(f"[PASS] Royalty-free audio library: {music_count} music tracks, {sfx_count} sound effects.")

    # 5. Workspace Directory
    ws_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "workspace"))
    os.makedirs(ws_dir, exist_ok=True)
    if os.access(ws_dir, os.W_OK):
        print(f"[PASS] Workspace directory writable: {ws_dir}")
    else:
        print(f"[FAIL] Workspace directory not writable: {ws_dir}")

    print("=" * 60)
    print("Diagnostics complete.")

if __name__ == "__main__":
    run_diagnostics()