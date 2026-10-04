import os
import subprocess
from typing import Optional, List, Tuple
from models.metadata import VideoPackaging, ThumbnailConcept, YouTubeMetadata
from tools.cloudflare_image_tool import CloudflareFluxProvider
from utils.filesystem import WorkspaceManager
from utils.logging import get_logger

logger = get_logger("thumbnail_service")

class ThumbnailService:
    def __init__(self, flux_provider: Optional[CloudflareFluxProvider] = None):
        self.flux_provider = flux_provider or CloudflareFluxProvider()

    def generate_thumbnail(
        self,
        concept: ThumbnailConcept,
        workspace: WorkspaceManager,
        output_width: int = 1280,
        output_height: int = 720,
        aspect_ratio: str = "16:9"
    ) -> Tuple[bool, str]:
        """
        Creates a high-CTR YouTube thumbnail honoring target aspect ratio:
        1. Generates base image with Cloudflare FLUX
        2. Renders high-contrast bold typography with backing box using Pillow or FFmpeg
        """
        is_portrait = "9:16" in aspect_ratio or aspect_ratio == "portrait"
        actual_width = 720 if is_portrait else output_width
        actual_height = 1280 if is_portrait else output_height

        output_path = workspace.get_thumbnail_path()
        raw_base_path = os.path.join(workspace.thumbnail_dir, "raw_base.png")

        try:
            # Step 1: Generate base visual
            framing = "vertical portrait framing, centered composition, 9:16" if is_portrait else "wide 16:9 composition"
            prompt = f"{concept.visual_prompt}, ultra high quality YouTube thumbnail, dramatic lighting, intense composition, {framing}, 8k"
            logger.info(f"Generating thumbnail base image: '{prompt[:60]}...'")
            self.flux_provider.generate_image(prompt, raw_base_path, aspect_ratio=aspect_ratio)

            if not os.path.exists(raw_base_path):
                raise RuntimeError("Thumbnail base visual could not be generated")

            text = (concept.overlay_text or "REFLECT").upper().strip()

            # Try Pillow first if available
            try:
                from PIL import Image, ImageDraw, ImageFont
                return self._render_with_pillow(raw_base_path, output_path, text, actual_width, actual_height)
            except ImportError:
                # Use FFmpeg drawtext filter
                return self._render_with_ffmpeg(raw_base_path, output_path, text, actual_width, actual_height)

        except Exception as e:
            logger.error(f"Thumbnail creation error: {e}")
            return self._create_fallback(concept, output_path, actual_width, actual_height)

    def _render_with_pillow(self, raw_base: str, output_path: str, text: str, width: int, height: int) -> Tuple[bool, str]:
        from PIL import Image, ImageDraw, ImageFont
        with Image.open(raw_base) as img:
            img = img.convert("RGBA")
            img = img.resize((width, height), Image.Resampling.LANCZOS)

            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # Gradient overlay at bottom
            for y in range(int(height * 0.45), height):
                alpha = int(190 * ((y - height * 0.45) / (height * 0.55)))
                draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

            # Draw text
            font_size = 68
            font = None
            for fp in [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            ]:
                if os.path.exists(fp):
                    try:
                        font = ImageFont.truetype(fp, font_size)
                        break
                    except Exception:
                        pass
            if not font:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            pos_x = 60
            pos_y = height - th - 90
            pad = 22

            draw.rounded_rectangle([pos_x - pad, pos_y - pad, pos_x + tw + pad, pos_y + th + pad], radius=10, fill=(15, 23, 42, 240), outline=(245, 158, 11, 255), width=4)
            draw.text((pos_x, pos_y), text, font=font, fill=(255, 255, 255, 255))

            final_img = Image.alpha_composite(img, overlay)
            final_img.convert("RGB").save(output_path, "JPEG", quality=95)
            logger.info(f"Thumbnail rendered via Pillow: {output_path}")
            return True, output_path

    def _render_with_ffmpeg(self, raw_base: str, output_path: str, text: str, width: int, height: int) -> Tuple[bool, str]:
        # Escape text for FFmpeg
        clean_text = text.replace(":", "\\:").replace("'", "")
        vf = (
            f"scale={width}:{height},"
            f"drawbox=y=ih-180:color=black@0.65:width=iw:height=180:t=fill,"
            f"drawtext=text='{clean_text}':fontcolor=white:fontsize=56:box=1:boxcolor=0x0F172A@0.85:boxborderw=16:x=60:y=h-th-70"
        )
        cmd = [
            "ffmpeg",
            "-i", raw_base,
            "-vf", vf,
            "-frames:v", "1",
            "-y",
            output_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(output_path):
            logger.info(f"Thumbnail rendered via FFmpeg: {output_path}")
            return True, output_path
        else:
            # Fallback simple copy
            import shutil
            shutil.copy2(raw_base, output_path)
            return True, output_path

    def _create_fallback(self, concept: ThumbnailConcept, output_path: str, width: int, height: int) -> Tuple[bool, str]:
        cmd = [
            "ffmpeg",
            "-f", "lavfi",
            "-i", f"color=c=0x0F172A:s={width}x{height}:d=1",
            "-vf", f"drawtext=text='{concept.overlay_text or 'MUST WATCH'}':fontcolor=0xF59E0B:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2",
            "-frames:v", "1",
            "-y",
            output_path
        ]
        subprocess.run(cmd, capture_output=True)
        return True, output_path
