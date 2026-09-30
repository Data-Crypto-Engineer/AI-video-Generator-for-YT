import os
import base64
import json
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from utils.logging import get_logger
from utils.retry import retry_with_backoff, PermanentPipelineError, TransientPipelineError

logger = get_logger("cloudflare_image_tool")

class ImageProvider(ABC):
    @abstractmethod
    def generate_image(self, prompt: str, output_path: str, aspect_ratio: str = "16:9") -> Tuple[bool, str]:
        pass

class CloudflareFluxProvider(ImageProvider):
    """
    Production image generation via Cloudflare Workers AI:
    Model: @cf/black-forest-labs/flux-1-schnell
    """
    def __init__(self, account_id: Optional[str] = None, api_token: Optional[str] = None):
        self.account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID") or ""
        self.api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN") or ""
        self.model = "@cf/black-forest-labs/flux-1-schnell"
        self.api_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"

    @retry_with_backoff(max_retries=3, initial_delay=1.5, retry_on=(TransientPipelineError,))
    def generate_image(self, prompt: str, output_path: str, aspect_ratio: str = "16:9") -> Tuple[bool, str]:
        if not self.account_id or not self.api_token:
            raise PermanentPipelineError("Cloudflare credentials missing (CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN)")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        payload = {
            "prompt": prompt
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "User-Agent": "ai-video-agent/1.0"
        }

        req = urllib.request.Request(self.api_url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                resp_bytes = response.read()
                resp_json = json.loads(resp_bytes.decode("utf-8"))

                if not resp_json.get("success", False) and "result" not in resp_json:
                    errors = resp_json.get("errors", [])
                    err_msg = errors[0].get("message") if errors else "Unknown Cloudflare AI error"
                    logger.error(f"Cloudflare API returned error: {err_msg}")
                    raise TransientPipelineError(f"Cloudflare API error: {err_msg}")

                img_b64 = resp_json.get("result", {}).get("image")
                if not img_b64:
                    raise TransientPipelineError("No image data returned in Cloudflare response")

                img_bytes = base64.b64decode(img_b64)
                if len(img_bytes) < 1000:
                    raise TransientPipelineError(f"Generated image suspiciously small: {len(img_bytes)} bytes")

                with open(output_path, "wb") as f:
                    f.write(img_bytes)

                logger.info(f"Successfully generated visual: {output_path} ({len(img_bytes)} bytes)")
                return True, output_path

        except urllib.error.HTTPError as e:
            code = e.code
            err_body = e.read().decode("utf-8", errors="replace")
            if code in (401, 403):
                raise PermanentPipelineError(f"Cloudflare authentication failed (HTTP {code}): {err_body}")
            elif code in (400, 422):
                raise PermanentPipelineError(f"Cloudflare bad request parameters (HTTP {code}): {err_body}")
            else:
                raise TransientPipelineError(f"Cloudflare temporary error (HTTP {code}): {err_body}")
        except urllib.error.URLError as e:
            raise TransientPipelineError(f"Cloudflare network connection error: {e.reason}")
        except json.JSONDecodeError as e:
            raise TransientPipelineError(f"Failed to parse Cloudflare JSON response: {e}")

# Compatibility alias
CloudflareImageTool = CloudflareFluxProvider
