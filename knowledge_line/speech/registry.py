"""Pick and build STT / TTS providers from configuration."""

from __future__ import annotations

from ..config import Settings
from . import elevenlabs, gemini, google_cloud
from .base import ProviderNotConfigured, STTProvider, TTSProvider
from .mock import MockSTT, MockTTS
from .stubs import AzureSTT, AzureTTS, TildeSTT, TildeTTS

ALL = ("google", "elevenlabs", "gemini", "azure", "tilde", "mock")


def _is_available(name: str, settings: Settings) -> bool:
    if name == "mock":
        return True
    if name == "google":
        return google_cloud.configured()
    if name == "elevenlabs":
        return elevenlabs.configured()
    if name == "gemini":
        return gemini.configured()
    if name in ("azure", "tilde"):
        return bool(settings.get(f"providers.{name}.enabled"))
    return False


def available_stt(settings: Settings) -> list[str]:
    return [n for n in ALL if _is_available(n, settings)]


available_tts = available_stt


def _resolve(kind: str, settings: Settings, requested: str | None) -> str:
    p = (requested or settings.get(f"{kind}.provider") or "auto").lower()
    if p != "auto":
        if p not in ALL:
            raise ValueError(f"Unknown {kind} provider '{p}'. Choose from {ALL}")
        return p
    for cand in settings.get(f"{kind}.fallback_order", ["mock"]):
        if _is_available(cand, settings):
            return cand
    return "mock"


def make_stt(settings: Settings, provider: str | None = None) -> STTProvider:
    p = _resolve("stt", settings, provider)
    cfg = settings.get(f"providers.{p}", {}) or {}
    if p == "google":
        return google_cloud.GoogleSTT(model=cfg.get("stt_model"))
    if p == "elevenlabs":
        return elevenlabs.ElevenLabsSTT(model=cfg.get("stt_model", "scribe_v1"),
                                        language_code=cfg.get("language_code", settings.lang))
    if p == "gemini":
        return gemini.GeminiSTT(model=cfg.get("stt_model", "gemini-2.5-flash"))
    if p == "azure":
        return AzureSTT(**cfg)
    if p == "tilde":
        return TildeSTT(**cfg)
    return MockSTT()


def make_tts(settings: Settings, provider: str | None = None) -> TTSProvider:
    p = _resolve("tts", settings, provider)
    cfg = settings.get(f"providers.{p}", {}) or {}
    if p == "google":
        return google_cloud.GoogleTTS(voice=cfg.get("tts_voice") or None,
                                      audio_encoding=cfg.get("tts_audio_encoding", "MP3"))
    if p == "elevenlabs":
        return elevenlabs.ElevenLabsTTS(model=cfg.get("tts_model", "eleven_v4_turbo"), voice_id=cfg.get("voice_id") or None,
                                        language_code=cfg.get("language_code", settings.lang),
                                        output_format=cfg.get("output_format", "mp3_44100_128"))
    if p == "gemini":
        return gemini.GeminiTTS(model=cfg.get("tts_model", "gemini-2.5-flash-preview-tts"), voice=cfg.get("tts_voice", "Kore"))
    if p == "azure":
        return AzureTTS(**cfg)
    if p == "tilde":
        return TildeTTS(**cfg)
    return MockTTS()


__all__ = ["make_stt", "make_tts", "available_stt", "available_tts", "ProviderNotConfigured"]
