"""Speech to text: Muse Voice Transcribe (Meta Model API) or an offline mock.

Muse Voice Transcribe accepts WAV only (RIFF, mono, 16-bit PCM, 16 or 24 kHz); the web page
records and converts in the browser, so the server never needs ffmpeg.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

import httpx

MAX_AUDIO_BYTES = 10 * 1024 * 1024


class SpeechError(RuntimeError):
    pass


class Transcriber(Protocol):
    name: str

    def transcribe(self, wav: bytes) -> str: ...


def check_wav(wav: bytes) -> None:
    if len(wav) > MAX_AUDIO_BYTES:
        raise SpeechError("audio too long")
    if len(wav) < 44 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise SpeechError("audio must be a WAV file")


@dataclass
class MetaTranscriber:
    api_key: str
    base_url: str = "https://api.meta.ai/v1"
    model: str = "muse-voice-transcribe-1.0"
    timeout: float = 60.0
    client: httpx.Client | None = None
    name: str = "meta"

    def transcribe(self, wav: bytes) -> str:
        check_wav(wav)
        if not self.api_key:
            raise SpeechError("MODEL_API_KEY is not set")
        request = {"mode": "PUSH_TO_TALK", "model": self.model, "audioEncoding": "WAV",
                   "languageBias": ["Arabic", "French"], "keywords": ["Wfarhali", "TEMU"]}
        files = {"request": (None, json.dumps(request), "application/json"), "audio": ("voice.wav", wav, "audio/wav")}
        client = self.client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(f"{self.base_url}/asr/transcribe", files=files,
                                   headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"})
        finally:
            if self.client is None:
                client.close()
        if response.status_code >= 400:
            raise SpeechError(f"Muse Voice Transcribe {response.status_code}: {response.text[:200]}")
        return str(response.json().get("transcript") or "").strip()


@dataclass
class MockTranscriber:
    """Offline: returns a fixed Darija sentence so the voice flow can be demonstrated without an API."""
    sentence: str = "حاب صباط أبيض مقاس 40 وروبة صيف، الميزانية 15 ألف، والتوصيل لباتنة"
    name: str = "mock"

    def transcribe(self, wav: bytes) -> str:
        check_wav(wav)
        return self.sentence


def from_settings(settings) -> Transcriber:
    if settings.stt == "meta":
        return MetaTranscriber(api_key=settings.model_api_key, base_url=settings.meta_base_url)
    return MockTranscriber()
