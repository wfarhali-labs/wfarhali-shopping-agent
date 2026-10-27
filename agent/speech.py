"""Speech to text: Muse Voice Transcribe (Meta Model API) or an offline mock.

Muse Voice Transcribe accepts WAV only (RIFF, mono, 16-bit PCM, 16 or 24 kHz); the web page
records and converts in the browser, so the server never needs ffmpeg.
"""
from __future__ import annotations

import array
import json
import logging
import struct
from dataclasses import dataclass
from typing import Protocol

import httpx

MAX_AUDIO_BYTES = 10 * 1024 * 1024
SILENCE_PEAK = 0.01            # peak amplitude (0..1) under which a recording is treated as silent
log = logging.getLogger("wfagent.speech")


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


def wav_stats(wav: bytes) -> dict:
    """Duration and peak level of a 16-bit PCM WAV (what the browser sends), for diagnostics and the silence guard."""
    try:
        channels, rate, bits = struct.unpack("<H", wav[22:24])[0], struct.unpack("<I", wav[24:28])[0], struct.unpack("<H", wav[34:36])[0]
        pos = 12
        while pos + 8 <= len(wav) and wav[pos:pos + 4] != b"data":        # skip other chunks until the data chunk
            pos += 8 + struct.unpack("<I", wav[pos + 4:pos + 8])[0]
        data = wav[pos + 8:]
        if bits != 16 or not data:
            return {"seconds": 0.0, "peak": 0.0, "rate": rate, "channels": channels}
        samples = array.array("h"); samples.frombytes(data[:len(data) - len(data) % 2])
        peak = max((abs(v) for v in samples), default=0) / 32768
        seconds = len(samples) / max(1, rate * max(1, channels))
        return {"seconds": round(seconds, 2), "peak": round(peak, 4), "rate": rate, "channels": channels}
    except (struct.error, ValueError):
        return {"seconds": 0.0, "peak": 0.0, "rate": 0, "channels": 0}


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
        stats = wav_stats(wav)
        log.info("voice: %d bytes, %.2f s, %d Hz, %d ch, peak %.4f", len(wav), stats["seconds"], stats["rate"], stats["channels"], stats["peak"])
        if stats["peak"] < SILENCE_PEAK:                   # nothing was captured: say so instead of paying for an empty transcript
            raise SpeechError("silent recording: the microphone captured no sound")
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
        body = response.json()
        transcript = str(body.get("transcript") or "").strip()
        if not transcript:                                  # fall back to the per-turn texts, if the service only filled those
            transcript = " ".join(str(t.get("transcript") or t.get("text") or "") for t in body.get("turns") or []).strip()
        log.info("voice: Muse Voice Transcribe answered, audio %s ms, transcript %d chars", body.get("audioDurationMs"), len(transcript))
        return transcript


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
