"""Google Cloud Speech-to-Text (v1) and Text-to-Speech over REST.

Auth: a service account (GOOGLE_APPLICATION_CREDENTIALS path, or
GOOGLE_APPLICATION_CREDENTIALS_JSON inline) is preferred; an API key
(GOOGLE_CLOUD_API_KEY / GOOGLE_API_KEY) with the Speech/TTS APIs enabled
also works.
"""

from __future__ import annotations

import base64
import json
import os
import time
from functools import lru_cache

import httpx

from .base import ProviderNotConfigured, STTProvider, STTResult, TTSProvider, TTSResult, to_wav16k

SCOPE = "https://www.googleapis.com/auth/cloud-platform"
VOICE_PREFERENCE = ("Chirp3-HD", "Chirp-HD", "Neural2", "Wavenet", "Standard")


class _GoogleAuth:
    def __init__(self):
        self._creds = None
        self.api_key = os.environ.get("GOOGLE_CLOUD_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        inline = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if path or inline:
            from google.oauth2 import service_account

            info = json.loads(inline) if inline and not path else json.loads(open(path).read())
            self._creds = service_account.Credentials.from_service_account_info(info, scopes=[SCOPE])
        if not self._creds and not self.api_key:
            raise ProviderNotConfigured("Google Cloud speech needs GOOGLE_APPLICATION_CREDENTIALS or an API key")
        self.project = getattr(self._creds, "project_id", None)

    def request_kwargs(self) -> dict:
        if self._creds:
            from google.auth.transport.requests import Request

            if not self._creds.valid:
                self._creds.refresh(Request())
            headers = {"Authorization": f"Bearer {self._creds.token}"}
            if self.project:
                headers["x-goog-user-project"] = self.project
            return {"headers": headers}
        return {"params": {"key": self.api_key}}


@lru_cache(maxsize=1)
def _auth() -> _GoogleAuth:
    return _GoogleAuth()


def configured() -> bool:
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    return bool(
        (path and os.path.isfile(os.path.expanduser(path)))
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        or os.environ.get("GOOGLE_CLOUD_API_KEY")
    )


class GoogleSTT(STTProvider):
    name = "google"
    URL = "https://speech.googleapis.com/v1/speech:recognize"

    def __init__(self, model: str | None = "latest_long"):
        self.model = model or None
        self.auth = _auth()

    def transcribe(self, audio: bytes, mime: str = "audio/wav", language: str = "lt-LT") -> STTResult:
        wav = to_wav16k(audio, mime)
        t0 = time.perf_counter()
        cfg = {"encoding": "LINEAR16", "sampleRateHertz": 16000, "languageCode": language,
               "enableAutomaticPunctuation": True}
        if self.model:
            cfg["model"] = self.model
        body = {"config": cfg, "audio": {"content": base64.b64encode(wav[44:] if wav[:4] == b"RIFF" else wav).decode()}}
        r = httpx.post(self.URL, json=body, timeout=60, **self.auth.request_kwargs())
        if r.status_code == 400 and self.model:  # model not available for this language
            cfg.pop("model")
            r = httpx.post(self.URL, json=body, timeout=60, **self.auth.request_kwargs())
        r.raise_for_status()
        data = r.json()
        alts = [res["alternatives"][0] for res in data.get("results", []) if res.get("alternatives")]
        text = " ".join(a.get("transcript", "").strip() for a in alts).strip()
        conf = alts[0].get("confidence") if alts else None
        return STTResult(text=text, provider=self.name, language=language, confidence=conf,
                         latency_ms=(time.perf_counter() - t0) * 1000, raw={"model": cfg.get("model", "default")})


class GoogleTTS(TTSProvider):
    name = "google"
    URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

    def __init__(self, voice: str | None = None, audio_encoding: str = "MP3"):
        self.auth = _auth()
        self.voice = voice or None
        self.audio_encoding = audio_encoding

    def list_voices(self, language: str = "lt-LT") -> list[dict]:
        r = httpx.get("https://texttospeech.googleapis.com/v1/voices", timeout=30,
                      **_merge(self.auth.request_kwargs(), {"params": {"languageCode": language}}))
        r.raise_for_status()
        return r.json().get("voices", [])

    def pick_voice(self, language: str) -> str:
        voices = [v["name"] for v in self.list_voices(language)]
        for pref in VOICE_PREFERENCE:
            for v in sorted(voices):
                if pref in v:
                    return v
        if not voices:
            raise ProviderNotConfigured(f"No Google TTS voice for {language}")
        return voices[0]

    def synthesize(self, text: str, language: str = "lt-LT", speaking_rate: float = 1.0) -> TTSResult:
        voice = self.voice or self.pick_voice(language)
        self.voice = voice
        t0 = time.perf_counter()
        body = {"input": {"text": text}, "voice": {"languageCode": language, "name": voice},
                "audioConfig": {"audioEncoding": self.audio_encoding, "speakingRate": speaking_rate}}
        r = httpx.post(self.URL, json=body, timeout=60, **self.auth.request_kwargs())
        if r.status_code == 400 and speaking_rate != 1.0:
            body["audioConfig"].pop("speakingRate")
            r = httpx.post(self.URL, json=body, timeout=60, **self.auth.request_kwargs())
        r.raise_for_status()
        audio = base64.b64decode(r.json()["audioContent"])
        mime = "audio/mpeg" if self.audio_encoding == "MP3" else "audio/wav"
        return TTSResult(audio=audio, mime=mime, provider=self.name, voice=voice,
                         latency_ms=(time.perf_counter() - t0) * 1000, spoken_text=text)


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = {**out.get(k, {}), **v}
    return out
