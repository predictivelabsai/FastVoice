"""Google Gemini speech (Gemini API key): native TTS and audio transcription.

Useful when only a Gemini API key is available (no Google Cloud project with
Speech/TTS enabled). Lithuanian works for both directions.
"""

from __future__ import annotations

import base64
import io
import os
import time
import wave

import httpx

from .base import ProviderNotConfigured, STTProvider, STTResult, TTSProvider, TTSResult

API = "https://generativelanguage.googleapis.com/v1beta/models"


def _key() -> str:
    k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not k:
        raise ProviderNotConfigured("GEMINI_API_KEY is not set")
    return k


def configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _pcm_to_wav(pcm: bytes, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class GeminiTTS(TTSProvider):
    name = "gemini"

    def __init__(self, model: str = "gemini-2.5-flash-preview-tts", voice: str = "Kore"):
        self.key = _key()
        self.model = model
        self.voice = voice

    def synthesize(self, text: str, language: str = "lt-LT", speaking_rate: float = 1.0) -> TTSResult:
        t0 = time.perf_counter()
        slow = speaking_rate < 0.95
        body = {
            "contents": [{"parts": [{"text": f"Say slowly and clearly: {text}" if slow else text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self.voice}}}},
        }
        r = httpx.post(f"{API}/{self.model}:generateContent", params={"key": self.key}, json=body, timeout=120)
        r.raise_for_status()
        part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        rate = 24000
        if "rate=" in part.get("mimeType", ""):
            rate = int(part["mimeType"].split("rate=")[1].split(";")[0])
        audio = _pcm_to_wav(base64.b64decode(part["data"]), rate)
        return TTSResult(audio=audio, mime="audio/wav", provider=self.name, voice=f"{self.model}/{self.voice}",
                         latency_ms=(time.perf_counter() - t0) * 1000, spoken_text=text)


class GeminiSTT(STTProvider):
    name = "gemini"

    def __init__(self, model: str = "gemini-2.5-flash"):
        self.key = _key()
        self.model = model

    def transcribe(self, audio: bytes, mime: str = "audio/wav", language: str = "lt-LT") -> STTResult:
        t0 = time.perf_counter()
        prompt = ("Transcribe this speech verbatim in its original language (expected: "
                  f"{language}). Output only the transcript, no commentary.")
        body = {"contents": [{"parts": [{"text": prompt},
                                        {"inlineData": {"mimeType": mime, "data": base64.b64encode(audio).decode()}}]}],
                "generationConfig": {"temperature": 0}}
        r = httpx.post(f"{API}/{self.model}:generateContent", params={"key": self.key}, json=body, timeout=120)
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"].get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        return STTResult(text=text, provider=self.name, language=language,
                         latency_ms=(time.perf_counter() - t0) * 1000, raw={"model": self.model})
