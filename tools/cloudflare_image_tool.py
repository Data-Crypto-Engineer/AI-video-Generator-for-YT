import os
import json
import base64
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Tuple, Optional
from utils.logging import get_logger

logger = get_logger("cloudflare_image_tool")

class ImageProvider(ABC):
    @abstractmethod
    def generate_image(self, prompt: str, output_path: str) -> Tuple[bool, str]:
        pass

class CloudflareFluxProvider(ImageProvider):
    """
    Cloudflare Workers AI image generator.
    Supports FLUX.1-Schnell and SDXL-Lightning dynamically via environment or UI selection.
    """
    def __init__(
        self,
        account_id: Optional[str] = None,
        api_token: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self.api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN")
        # Defaults to SDXL-Lightning to save neurons, or reads from UI selection
        self.model = model or os.environ.get(
            "CLOUDFLARE_IMAGE_MODEL",
            "@cf/bytedance/stable-diffusion-xl-lightning"
        )

    def generate_image(self, prompt: str, output_path: str) -> Tuple[bool, str]:
        if not self.account_id or not self.api_token:
            raise ValueError("Cloudflare credentials (ACCOUNT_ID / API_TOKEN) missing")

        # Refresh model choice from environment if user changed it in the UI
        current_model = os.environ.get("CLOUDFLARE_IMAGE_MODEL", self.model)
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{current_model}"

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

        # Tailor payload parameters based on model
        if "lightning" in current_model.lower():
            payload = {"prompt": prompt, "num_steps": 4}
        else:
            payload = {"prompt": prompt, "num_steps": 8}

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = resp.read()
                content_type = resp.headers.get("Content-Type", "")

                # Binary image response
                if "image" in content_type:
                    with open(output_path, "wb") as f:
                        f.write(data)
                    return True, output_path

                # JSON response with image bytes
                resp_json = json.loads(data.decode("utf-8"))
                if resp_json.get("result", {}).get("image"):
                    img_bytes = base64.b64decode(resp_json["result"]["image"])
                    with open(output_path, "wb") as f:
                        f.write(img_bytes)
                    return True, output_path
                else:
                    raise RuntimeError(f"Unexpected Cloudflare response format: {data[:120]}")

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            # Mark daily exhaustion flag for UI probe
            if "10,000 neurons" in err_body or "4006" in err_body:
                os.environ["CLOUDFLARE_QUOTA_EXHAUSTED"] = "true"
            raise RuntimeError(f"Cloudflare error (HTTP {e.code}): {err_body}")
