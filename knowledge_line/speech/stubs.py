"""Stub adapters for Azure Speech and Tilde (disabled by default).

They define the configuration surface and fail loudly until implemented, so
deployments can switch to them later without touching the pipeline.
"""

from __future__ import annotations

from .base import ProviderNotConfigured, STTProvider, STTResult, TTSProvider, TTSResult


class _Stub:
    vendor = "stub"
    hint = ""

    def __init__(self, enabled: bool = False, **cfg):
        if not enabled:
            raise ProviderNotConfigured(f"{self.vendor} adapter is disabled (set enabled: true). {self.hint}")
        self.cfg = cfg

    def _todo(self):
        raise NotImplementedError(f"{self.vendor} adapter is a stub; implement REST calls here. {self.hint}")


class AzureSTT(_Stub, STTProvider):
    name = vendor = "azure"
    hint = "Azure Speech lt-LT: POST https://<region>.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1?language=lt-LT"

    def transcribe(self, audio: bytes, mime: str = "audio/wav", language: str = "lt-LT") -> STTResult:
        self._todo()


class AzureTTS(_Stub, TTSProvider):
    name = vendor = "azure"
    hint = "Azure neural voices lt-LT-OnaNeural / lt-LT-LeonasNeural via SSML."

    def synthesize(self, text: str, language: str = "lt-LT", speaking_rate: float = 1.0) -> TTSResult:
        self._todo()


class TildeSTT(_Stub, STTProvider):
    name = vendor = "tilde"
    hint = "Tilde ASR for Lithuanian (online or on-premise)."

    def transcribe(self, audio: bytes, mime: str = "audio/wav", language: str = "lt-LT") -> STTResult:
        self._todo()


class TildeTTS(_Stub, TTSProvider):
    name = vendor = "tilde"
    hint = "Tilde TTS for Lithuanian (online or on-premise)."

    def synthesize(self, text: str, language: str = "lt-LT", speaking_rate: float = 1.0) -> TTSResult:
        self._todo()
