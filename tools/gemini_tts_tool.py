import os
import base64
import json
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Optional, Tuple
from utils.logging import get_logger
from utils.retry import retry_with_backoff, PermanentPipelineError, TransientPipelineError
from utils.validation import validate_wav_audio, get_audio_duration

logger = get_logger("gemini_tts_tool")

class TTSProvider(ABC):
    @abstractmethod
    def generate_speech(
        self,
        text: str,
        output_path: str,
        voice_name: str = "Kore",
        style_direction: Optional[str] = None
    ) -> Tuple[bool, str, float]:
        pass

class GeminiTTSProvider(TTSProvider):
    """
    Production TTS via Google Gemini API:
    Model: gemini-3.8-flash-lite-tts
    Returns standard 24kHz 16-bit mono RIFF WAV bytes.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = "gemini-3.8-flash-lite-tts"
        self.endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

    @retry_with_backoff(max_retries=3, initial_delay=1.5, retry_on=(TransientPipelineError,))
    def generate_speech(
        self,
        text: str,
        output_path: str,
        voice_name: str = "Kore",
        style_direction: Optional[str] = None
    ) -> Tuple[bool, str, float]:
        if not self.api_key:
            raise PermanentPipelineError("Google Gemini API key missing (GEMINI_API_KEY)")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        url = f"{self.endpoint}?key={self.api_key}"

        # Gemini 3.8 Flash-Lite TTS schema
        prompt_text = text.strip()
        speech_style = style_direction or "Warm, calm, mature documentary narration. Natural conversational delivery."

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": prompt_text,
                            "speechMetadata": {
                                "style": speech_style
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                }
            }
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "aistudio-build"
        }

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=40) as response:
                resp_bytes = response.read()
                resp_json = json.loads(resp_bytes.decode("utf-8"))

                candidates = resp_json.get("candidates", [])
                if not candidates:
                    raise TransientPipelineError(f"No candidates in Gemini TTS response: {resp_json}")

                parts = candidates[0].get("content", {}).get("parts", [])
                audio_b64 = None
                for part in parts:
                    if "inlineData" in part and part["inlineData"].get("data"):
                        audio_b64 = part["inlineData"]["data"]
                        break

                if not audio_b64:
                    raise TransientPipelineError("No audio inlineData found in Gemini response parts")

                audio_bytes = base64.b64decode(audio_b64)
                if len(audio_bytes) < 100:
                    raise TransientPipelineError(f"Returned WAV audio data suspiciously small: {len(audio_bytes)} bytes")

                with open(output_path, "wb") as f:
                    f.write(audio_bytes)

                # Validate WAV stream with ffprobe
                valid, msg = validate_wav_audio(output_path)
                if not valid:
                    raise TransientPipelineError(f"WAV audio validation failed: {msg}")

                duration = get_audio_duration(output_path) or 0.0
                logger.info(f"Gemini TTS generated: {output_path} ({duration:.2f}s, voice={voice_name})")
                return True, output_path, duration

        except urllib.error.HTTPError as e:
            code = e.code
            err_body = e.read().decode("utf-8", errors="replace")
            if code in (401, 403):
                raise PermanentPipelineError(f"Gemini authentication failed (HTTP {code}): {err_body}")
            elif code == 404:
                raise PermanentPipelineError(f"Gemini TTS model not found (HTTP 404): {err_body}")
            elif code in (429, 500, 502, 503, 504):
                raise TransientPipelineError(f"Gemini temporary error (HTTP {code}): {err_body}")
            else:
                raise PermanentPipelineError(f"Gemini TTS error (HTTP {code}): {err_body}")
        except urllib.error.URLError as e:
            raise TransientPipelineError(f"Gemini connection error: {e.reason}")
