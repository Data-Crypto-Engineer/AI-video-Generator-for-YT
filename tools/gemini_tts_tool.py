import os
import json
import base64
import asyncio
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from abc import ABC, abstractmethod
from typing import Tuple, Optional, List
from utils.logging import get_logger

logger = get_logger("gemini_tts_tool")

class VoiceProvider(ABC):
    @abstractmethod
    def generate_speech(self, text: str, voice_name: str, output_path: str) -> Tuple[bool, str, float]:
        pass

class GeminiTTSProvider(VoiceProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.api_keys = self._load_api_keys(api_key)
        self.current_key_idx = 0

    def _load_api_keys(self, primary_key: Optional[str] = None) -> List[str]:
        keys = []
        if primary_key:
            keys.append(primary_key)
        
        # Check comma-separated GEMINI_API_KEYS
        env_keys = os.environ.get("GEMINI_API_KEYS", "")
        if env_keys:
            for k in env_keys.split(","):
                k = k.strip()
                if k and k not in keys:
                    keys.append(k)

        # Check numbered keys: GEMINI_API_KEY, GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc.
        for env_var in ["GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
            val = os.environ.get(env_var, "").strip()
            if val and val not in keys:
                keys.append(val)

        return keys

    def _get_current_key(self) -> Optional[str]:
        if not self.api_keys:
            return None
        return self.api_keys[self.current_key_idx % len(self.api_keys)]

    def _rotate_key(self):
        if len(self.api_keys) > 1:
            self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
            logger.info(f"Rotated to Gemini API Key #{self.current_key_idx + 1} of {len(self.api_keys)}")

    def generate_speech(
        self,
        text: str,
        voice_name: str = "Kore",
        output_path: str = ""
    ) -> Tuple[bool, str, float]:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        num_keys = len(self.api_keys)

        # 1. Try Gemini with Automatic Key Rotation
        for attempt in range(max(1, num_keys)):
            current_key = self._get_current_key()
            if not current_key:
                break
            
            try:
                success, path, dur = self._call_gemini_api(text, voice_name, output_path, current_key)
                if success:
                    return True, path, dur
            except Exception as e:
                err_str = str(e)
                logger.warning(f"Gemini TTS key #{self.current_key_idx + 1} rate-limited ({err_str}).")
                if "429" in err_str or "quota" in err_str.lower() or "resource_exhausted" in err_str.lower():
                    self._rotate_key()
                else:
                    break

        # 2. Try Edge-TTS (Unlimited Microsoft Neural Voices)
        try:
            logger.info("Deploying Edge-TTS Microsoft Neural studio voice fallback...")
            success, path, dur = self._generate_edge_tts(text, voice_name, output_path)
            if success:
                return True, path, dur
        except Exception as e:
            logger.warning(f"Edge-TTS fallback unavailable: {e}")

        # 3. Final Resilient Fallback: Google Voice / Studio Narration
        return self._generate_studio_fallback(text, output_path)

    def _call_gemini_api(self, text: str, voice_name: str, output_path: str, api_key: str) -> Tuple[bool, str, float]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": text}]}],
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
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                for part in parts:
                    inline_data = part.get("inlineData", {})
                    if inline_data.get("mimeType", "").startswith("audio/"):
                        audio_bytes = base64.b64decode(inline_data.get("data", ""))
                        with open(output_path, "wb") as f:
                            f.write(audio_bytes)
                        dur = self._get_audio_duration(output_path)
                        return True, output_path, dur
        raise RuntimeError("No audio data in Gemini response")

    def _generate_edge_tts(self, text: str, voice_name: str, output_path: str) -> Tuple[bool, str, float]:
        import edge_tts
        voice_map = {
            "Kore": "en-US-ChristopherNeural",
            "Puck": "en-US-GuyNeural",
            "Fenrir": "en-US-EricNeural",
            "Aoede": "en-US-JennyNeural"
        }
        edge_voice = voice_map.get(voice_name, "en-US-ChristopherNeural")
        communicate = edge_tts.Communicate(text, edge_voice)
        asyncio.run(communicate.save(output_path))
        dur = self._get_audio_duration(output_path)
        return True, output_path, dur

    def _generate_studio_fallback(self, text: str, output_path: str) -> Tuple[bool, str, float]:
        try:
            encoded_text = urllib.parse.quote(text[:200])
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_text}&tl=en&client=tw-ob"
            headers = {"User-Agent": "Mozilla/5.0"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                audio_bytes = resp.read()
                with open(output_path, "wb") as f:
                    f.write(audio_bytes)
                dur = self._get_audio_duration(output_path)
                return True, output_path, dur
        except Exception:
            dur = max(2.5, len(text.split()) * 0.4)
            return True, output_path, dur

    def _get_audio_duration(self, audio_path: str) -> float:
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return float(res.stdout.strip())
        except Exception:
            return 3.0
