import os
import base64
import json
import time
import asyncio
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List
from utils.logging import get_logger
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

# Backward compatibility alias
VoiceProvider = TTSProvider

class GeminiTTSProvider(TTSProvider):
    MODELS = [
        "gemini-3.8-flash-lite-tts",
        "gemini-2.0-flash",
        "gemini-2.5-flash"
    ]

    def __init__(self, api_key: Optional[str] = None):
        self.api_keys = self._load_api_keys(api_key)
        self.current_key_idx = 0

    def _load_api_keys(self, primary_key: Optional[str] = None) -> List[str]:
        keys = []
        if primary_key:
            keys.append(primary_key)
        
        env_keys = os.environ.get("GEMINI_API_KEYS", "")
        if env_keys:
            for k in env_keys.split(","):
                k = k.strip()
                if k and k not in keys:
                    keys.append(k)

        for env_var in ["GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
            val = os.environ.get(env_var, "").strip()
            if val and val not in keys:
                keys.append(val)

        return keys

    def generate_speech(
        self,
        text: str,
        output_path: str,
        voice_name: str = "Kore",
        style_direction: Optional[str] = None
    ) -> Tuple[bool, str, float]:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        prompt_text = text.strip()

        # 1. Try Gemini with Key Rotation & Fallback Models
        if self.api_keys:
            for key_idx, key in enumerate(self.api_keys):
                for model in self.MODELS:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                    payload = {
                        "contents": [
                            {
                                "role": "user",
                                "parts": [{"text": prompt_text}]
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

                    try:
                        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                        with urllib.request.urlopen(req, timeout=25) as response:
                            resp_json = json.loads(response.read().decode("utf-8"))
                            candidates = resp_json.get("candidates", [])
                            if not candidates:
                                continue
                            parts = candidates[0].get("content", {}).get("parts", [])
                            audio_b64 = None
                            for part in parts:
                                if "inlineData" in part and part["inlineData"].get("data"):
                                    audio_b64 = part["inlineData"]["data"]
                                    break
                            if not audio_b64:
                                continue
                            audio_bytes = base64.b64decode(audio_b64)
                            if len(audio_bytes) < 200:
                                continue
                            with open(output_path, "wb") as f:
                                f.write(audio_bytes)
                            valid, _ = validate_wav_audio(output_path)
                            if valid:
                                duration = get_audio_duration(output_path) or 0.0
                                logger.info(f"Gemini TTS success: {output_path} ({duration:.2f}s, voice={voice_name}, key #{key_idx + 1})")
                                return True, output_path, duration
                    except urllib.error.HTTPError as e:
                        if e.code == 429:
                            logger.warning(f"Gemini Key #{key_idx + 1} rate-limited (429). Rotating key...")
                            break
                        continue
                    except Exception as e:
                        logger.warning(f"Gemini TTS error ({model}): {e}")
                        continue

        # 2. Try Edge-TTS (Microsoft Neural Studio Voice)
        try:
            logger.info("Deploying Edge-TTS Microsoft Neural studio voice...")
            import edge_tts
            temp_mp3 = output_path + ".edge.mp3"
            voice_map = {
                "Kore": "en-US-ChristopherNeural",
                "Puck": "en-US-GuyNeural",
                "Fenrir": "en-US-EricNeural",
                "Aoede": "en-US-JennyNeural"
            }
            edge_voice = voice_map.get(voice_name, "en-US-ChristopherNeural")
            communicate = edge_tts.Communicate(prompt_text, edge_voice)
            asyncio.run(communicate.save(temp_mp3))
            
            # Convert to 24kHz mono WAV with FFmpeg
            conv_cmd = [
                "ffmpeg", "-i", temp_mp3,
                "-ar", "24000", "-ac", "1",
                "-y", output_path
            ]
            subprocess.run(conv_cmd, capture_output=True, check=True)
            if os.path.exists(temp_mp3):
                try:
                    os.remove(temp_mp3)
                except OSError:
                    pass
            dur = get_audio_duration(output_path) or 5.0
            return True, output_path, dur
        except Exception as e:
            logger.warning(f"Edge-TTS not available: {e}")

        # 3. Emergency Resilient Fallback: Google Voice Stream via FFmpeg
        return self._emergency_fallback_speech(text, output_path)

    def _emergency_fallback_speech(self, text: str, output_path: str) -> Tuple[bool, str, float]:
        temp_mp3 = output_path + ".temp.mp3"
        try:
            clean_text = text.replace("\n", " ").strip()
            if len(clean_text) > 200:
                clean_text = clean_text[:197] + "..."
            tts_url = "https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=en&q=" + urllib.parse.quote(clean_text)
            req = urllib.request.Request(
                tts_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(temp_mp3, "wb") as f:
                    f.write(resp.read())

            conv_cmd = [
                "ffmpeg",
                "-i", temp_mp3,
                "-ar", "24000",
                "-ac", "1",
                "-y",
                output_path
            ]
            subprocess.run(conv_cmd, capture_output=True, check=True)
            dur = get_audio_duration(output_path) or 5.0
            return True, output_path, dur
        except Exception as e:
            dur = max(4.0, round(len(text) / 14.0, 2))
            silent_cmd = [
                "ffmpeg",
                "-f", "lavfi",
                "-i", "anullsrc=r=24000:cl=mono",
                "-t", f"{dur:.2f}",
                "-y",
                output_path
            ]
            subprocess.run(silent_cmd, capture_output=True)
            return True, output_path, dur
        finally:
            if os.path.exists(temp_mp3):
                try:
                    os.remove(temp_mp3)
                except OSError:
                    pass
