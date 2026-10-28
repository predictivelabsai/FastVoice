"""Provider-neutral speech interfaces."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class ProviderNotConfigured(RuntimeError):
    """Raised when a provider is selected but credentials / enablement are missing."""


@dataclass
class STTResult:
    text: str
    provider: str
    language: str | None = None
    confidence: float | None = None
    latency_ms: float = 0.0
    raw: dict = field(default_factory=dict)


@dataclass
class TTSResult:
    audio: bytes
    mime: str
    provider: str
    voice: str = ""
    latency_ms: float = 0.0
    spoken_text: str = ""

    @property
    def ext(self) -> str:
        return {"audio/mpeg": "mp3", "audio/wav": "wav", "audio/ogg": "ogg"}.get(self.mime, "bin")


class STTProvider(ABC):
    name = "base"

    @abstractmethod
    def transcribe(self, audio: bytes, mime: str = "audio/wav", language: str = "lt-LT") -> STTResult: ...


class TTSProvider(ABC):
    name = "base"

    @abstractmethod
    def synthesize(self, text: str, language: str = "lt-LT", speaking_rate: float = 1.0) -> TTSResult: ...


def to_wav16k(audio: bytes, mime: str) -> bytes:
    """Convert any browser / file audio to 16 kHz mono LINEAR16 WAV via ffmpeg."""
    if mime in ("audio/wav", "audio/x-wav", "audio/l16") and audio[:4] == b"RIFF":
        src_is_wav = True
    else:
        src_is_wav = False
    if not shutil.which("ffmpeg"):
        if src_is_wav:
            return audio
        raise RuntimeError("ffmpeg is required to convert non-WAV audio")
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "in.bin"
        dst = Path(d) / "out.wav"
        src.write_bytes(audio)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "16000",
             "-sample_fmt", "s16", str(dst)],
            check=True,
        )
        return dst.read_bytes()


def to_telephony(audio: bytes) -> bytes:
    """Simulate a phone channel: 8 kHz mono G.711 mu-law, returned as WAV (for WER-over-phone tests)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for telephony simulation")
    with tempfile.TemporaryDirectory() as d:
        src, mid, dst = Path(d) / "in.bin", Path(d) / "mid.wav", Path(d) / "out.wav"
        src.write_bytes(audio)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "8000",
                        "-acodec", "pcm_mulaw", str(mid)], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mid), "-ac", "1", "-ar", "16000",
                        "-sample_fmt", "s16", str(dst)], check=True)
        return dst.read_bytes()
