"""Offline mock speech providers (no network, deterministic)."""

from __future__ import annotations

import io
import math
import struct
import time
import wave

from .base import STTProvider, STTResult, TTSProvider, TTSResult

MAGIC = b"KLTX"  # mock TTS embeds the text so mock STT can "recognise" it


class MockTTS(TTSProvider):
    name = "mock"

    def synthesize(self, text: str, language: str = "lt-LT", speaking_rate: float = 1.0) -> TTSResult:
        t0 = time.perf_counter()
        rate = 16000
        seconds = min(30.0, max(0.5, len(text) / (14.0 * speaking_rate)))
        n = int(rate * seconds)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            frames = bytearray()
            for i in range(n):  # soft 220 Hz tone with a gentle envelope
                env = min(1.0, i / 800, (n - i) / 800)
                frames += struct.pack("<h", int(1200 * env * math.sin(2 * math.pi * 220 * i / rate)))
            w.writeframes(bytes(frames))
        payload = text.encode("utf-8")
        audio = buf.getvalue() + MAGIC + struct.pack("<I", len(payload)) + payload
        return TTSResult(audio=audio, mime="audio/wav", provider=self.name, voice="sine-220",
                         latency_ms=(time.perf_counter() - t0) * 1000, spoken_text=text)


class MockSTT(STTProvider):
    name = "mock"

    def __init__(self, default_text: str = ""):
        self.default_text = default_text

    def transcribe(self, audio: bytes, mime: str = "audio/wav", language: str = "lt-LT") -> STTResult:
        t0 = time.perf_counter()
        idx = audio.rfind(MAGIC)
        if idx >= 0:
            (ln,) = struct.unpack("<I", audio[idx + 4: idx + 8])
            text = audio[idx + 8: idx + 8 + ln].decode("utf-8")
        else:
            text = self.default_text
        return STTResult(text=text, provider=self.name, language=language,
                         latency_ms=(time.perf_counter() - t0) * 1000)
