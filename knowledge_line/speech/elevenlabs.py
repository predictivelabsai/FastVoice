"""ElevenLabs Scribe (STT) and ElevenLabs TTS over REST."""

from __future__ import annotations

import os
import time

import httpx

from .base import ProviderNotConfigured, STTProvider, STTResult, TTSProvider, TTSResult

API = "https://api.elevenlabs.io/v1"
LANG_CODE_MODELS = ("eleven_flash_v2_5", "eleven_turbo_v2_5", "eleven_v3", "eleven_v4", "eleven_v4_turbo", "eleven_multilingual_v2")


def _key() -> str:
    k = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("XI_API_KEY")
    if not k:
        raise ProviderNotConfigured("ELEVENLABS_API_KEY is not set")
    return k


def configured() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("XI_API_KEY"))


class ElevenLabsSTT(STTProvider):
    name = "elevenlabs"

    def __init__(self, model: str = "scribe_v1", language_code: str = "lt"):
        self.key = _key()
        self.model = model
        self.language_code = language_code

    def transcribe(self, audio: bytes, mime: str = "audio/wav", language: str = "lt-LT") -> STTResult:
        t0 = time.perf_counter()
        lang = self.language_code or language.split("-")[0]
        files = {"file": ("audio", audio, mime)}
        data = {"model_id": self.model, "language_code": lang, "tag_audio_events": "false"}
        r = httpx.post(f"{API}/speech-to-text", headers={"xi-api-key": self.key}, files=files, data=data, timeout=120)
        r.raise_for_status()
        j = r.json()
        return STTResult(text=(j.get("text") or "").strip(), provider=self.name,
                         language=j.get("language_code"), confidence=j.get("language_probability"),
                         latency_ms=(time.perf_counter() - t0) * 1000, raw={"model": self.model})


class ElevenLabsTTS(TTSProvider):
    name = "elevenlabs"

    def __init__(self, model: str = "eleven_v4_turbo", voice_id: str | None = None, language_code: str = "lt",
                 output_format: str = "mp3_44100_128"):
        self.key = _key()
        self.model = model
        self.voice_id = voice_id or None
        self.language_code = language_code
        self.output_format = output_format

    def _default_voice(self) -> str:
        r = httpx.get(f"{API}/voices", headers={"xi-api-key": self.key}, timeout=30)
        r.raise_for_status()
        voices = r.json().get("voices", [])
        if not voices:
            raise ProviderNotConfigured("No ElevenLabs voices on this account")
        premade = [v for v in voices if v.get("category") == "premade"] or voices
        return premade[0]["voice_id"]

    def synthesize(self, text: str, language: str = "lt-LT", speaking_rate: float = 1.0) -> TTSResult:
        voice = self.voice_id or self._default_voice()
        self.voice_id = voice
        t0 = time.perf_counter()
        body: dict = {"text": text, "model_id": self.model}
        if self.model in LANG_CODE_MODELS and self.language_code:
            body["language_code"] = self.language_code
        if speaking_rate != 1.0:
            body["voice_settings"] = {"speed": max(0.7, min(1.2, speaking_rate))}
        url = f"{API}/text-to-speech/{voice}"
        hdr = {"xi-api-key": self.key, "accept": "audio/mpeg"}
        r = httpx.post(url, params={"output_format": self.output_format}, headers=hdr, json=body, timeout=120)
        if r.status_code in (400, 422) and "language_code" in body:
            body.pop("language_code")
            r = httpx.post(url, params={"output_format": self.output_format}, headers=hdr, json=body, timeout=120)
        r.raise_for_status()
        return TTSResult(audio=r.content, mime="audio/mpeg", provider=self.name, voice=voice,
                         latency_ms=(time.perf_counter() - t0) * 1000, spoken_text=text)
