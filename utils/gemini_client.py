import os
import json
import re
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from utils.logging import get_logger
from utils.retry import retry_with_backoff, PermanentPipelineError, TransientPipelineError

logger = get_logger("gemini_client")

class GeminiReasoningClient:
    """
    Client for high-level agent reasoning, screenplay decomposition,
    music selection reasoning, and packaging strategy.
    Uses gemini-3.1-flash-lite for instant zero-latency responses with fallback to gemini-3.8-flash.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.primary_model = "gemini-3.1-flash-lite"
        self.fallback_model = "gemini-3.8-flash"

    def generate_json_response(self, prompt: str, system_instruction: Optional[str] = None) -> Dict[str, Any]:
        """Sends prompt and extracts pure parsed JSON response."""
        for model in [self.primary_model, self.fallback_model]:
            try:
                raw_text = self._call_model(model, prompt, system_instruction)
                parsed = self._extract_json(raw_text)
                if parsed:
                    return parsed
            except Exception as e:
                logger.warning(f"Model {model} failed ({e}), trying fallback if available...")
                continue

        # If both failed or returned invalid JSON, raise
        raise RuntimeError("All Gemini reasoning models failed to generate valid structured JSON.")

    def _call_model(self, model: str, prompt: str, system_instruction: Optional[str] = None) -> str:
        if not self.api_key:
            raise PermanentPipelineError("GEMINI_API_KEY is not set.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "aistudio-build"
        }

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            candidates = body.get("candidates", [])
            if not candidates:
                raise TransientPipelineError(f"No candidates returned by {model}: {body}")
            parts = candidates[0].get("content", {}).get("parts", [])
            for p in parts:
                if "text" in p:
                    return p["text"]
            raise TransientPipelineError("No text found in candidate parts.")

    def _extract_json(self, raw_text: str) -> Optional[Dict[str, Any]]:
        text = raw_text.strip()
        # Remove markdown codeblocks if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\n?```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to locate first '{' and last '}'
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end+1])
                except Exception:
                    pass
        return None
