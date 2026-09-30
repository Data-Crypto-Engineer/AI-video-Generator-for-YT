import os
import json
import base64
import urllib.request
import urllib.error
from typing import Optional, Dict, Any
from utils.logging import get_logger
from utils.retry import retry_with_backoff, PermanentPipelineError, TransientPipelineError

logger = get_logger("cloudflare_image_tool")

class CloudflareImageTool:
    """
    Cloudflare Workers AI FLUX Schnell Image Generation Tool.
    Model: @cf/black-forest-labs/flux-1-schnell
    """
    def __init__(self, account_id: Optional[str] = None, api_token: Optional[str] = None):
        self.account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID") or ""
        self.api_token = api_token or os.environ.get("CLOUDFLARE_API_TOKEN") or ""
        self.model = "@cf/black-forest-labs/flux-1-schnell"
        self.api_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"

    @retry_with_backoff(max_retries=3, initial_delay=2.0)
    def generate_image(self, prompt: str, output_path: str, steps: int = 4) -> str:
        if not self.account_id or not self.api_token:
            raise PermanentPipelineError("CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN is missing.")

        payload = {
            "prompt": prompt,
            "num_steps": min(max(steps, 4), 8)
        }
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self.api_url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                content_type = response.headers.get("Content-Type", "")
                resp_bytes = response.read()

                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                if "image/" in content_type:
                    with open(output_path, "wb") as f:
                        f.write(resp_bytes)
                else:
                    try:
                        resp_json = json.loads(resp_bytes.decode("utf-8"))
                        if "result" in resp_json and "image" in resp_json["result"]:
                            img_b64 = resp_json["result"]["image"]
                            img_data = base64.b64decode(img_b64)
                            with open(output_path, "wb") as f:
                                f.write(img_data)
                        else:
                            raise PermanentPipelineError(f"Unexpected Cloudflare response format: {resp_json}")
                    except Exception as json_err:
                        with open(output_path, "wb") as f:
                            f.write(resp_bytes)

                if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
                    raise TransientPipelineError(f"Generated image empty or corrupt: {output_path}")

                logger.info(f"Successfully generated visual: {output_path} ({os.path.getsize(output_path)} bytes)")
                return output_path

        except urllib.error.HTTPError as http_err:
            if http_err.code in (401, 403):
                raise PermanentPipelineError(f"Cloudflare authentication failed (HTTP {http_err.code}). Check credentials.")
            elif http_err.code in (429, 500, 502, 503, 504):
                raise TransientPipelineError(f"Cloudflare temporary error HTTP {http_err.code}: {http_err.reason}")
            else:
                raise PermanentPipelineError(f"Cloudflare client error HTTP {http_err.code}: {http_err.reason}")
        except Exception as e:
            if isinstance(e, (PermanentPipelineError, TransientPipelineError)):
                raise e
            raise TransientPipelineError(f"Network error communicating with Cloudflare AI: {str(e)}")