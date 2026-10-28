import io
import struct

from fastapi.testclient import TestClient

import web.app as webapp

client = TestClient(webapp.app)


def _wav(seconds=0.2, rate=24000):
    frames = int(seconds * rate)
    data = struct.pack(f"<{frames}h", *([0] * frames))
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    return header + b"data" + struct.pack("<I", len(data)) + data


def test_page_and_health():
    assert "واش حاب تشري اليوم" in client.get("/").text
    health = client.get("/api/health").json()
    assert {k: health[k] for k in ("ok", "model", "catalogue", "speech", "segment")} == {"ok": True, "model": "mock", "catalogue": "demo", "speech": "mock", "segment": "mock"}
    assert health["model_id"] == "muse-spark-1.3" and health["base_url"].startswith("https://") and "key_set" in health
    assert health["whatsapp"].isdigit() or health["whatsapp"] == ""
    assert client.get("/static/app.js").status_code == 200


def test_text_turn_then_follow_up_keeps_the_conversation():
    first = client.post("/api/turn", data={"text": "عندي عرس الجمعة"}).json()
    assert first["status"] == "question" and first["session_id"]
    second = client.post("/api/turn", data={"text": "روبة سهرة بـ مليون و200", "session_id": first["session_id"]}).json()
    assert second["status"] == "proposal" and second["session_id"] == first["session_id"]
    assert second["proposal"]["items"][0]["need"] == "dress"
    assert "messages" not in second                                    # the raw conversation stays on the server


def test_voice_turn_goes_through_the_transcriber():
    response = client.post("/api/turn", files={"audio": ("voice.wav", _wav(), "audio/wav")}).json()
    assert response["transcript"].startswith("حاب صباط") and response["status"] == "proposal"
    bad = client.post("/api/turn", files={"audio": ("voice.wav", b"not audio", "audio/wav")})
    assert bad.status_code == 422 and "WAV" in bad.json()["error"]


def test_photo_turn_and_input_guards():
    photo = client.post("/api/turn", files={"image": ("p.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")}).json()
    assert photo["status"] == "question"
    assert client.post("/api/turn", files={"image": ("p.txt", b"hello", "text/plain")}).status_code == 415
    assert client.post("/api/turn", files={"image": ("p.png", io.BytesIO(b"0" * (webapp.MAX_IMAGE_BYTES + 1)), "image/png")}).status_code == 413
    assert client.post("/api/turn", data={"text": "  "}).status_code == 422


def test_voice_empty_transcript_and_silence_guard(monkeypatch):
    class Silent:
        name = "mock"

        def transcribe(self, wav):
            return ""
    monkeypatch.setattr(webapp, "transcriber", Silent())
    empty = client.post("/api/turn", files={"audio": ("voice.wav", _wav(), "audio/wav")})
    assert empty.status_code == 422 and "nothing understood" in empty.json()["error"]
    # the Meta client refuses a silent recording before spending anything
    import httpx
    from agent.speech import MetaTranscriber, SpeechError, wav_stats
    silent = _wav(seconds=1.0)
    assert wav_stats(silent) == {"seconds": 1.0, "peak": 0.0, "rate": 24000, "channels": 1}
    class NeverCalled(httpx.Client):
        def post(self, *a, **k):
            raise AssertionError("must not call the API for silence")
    try:
        MetaTranscriber(api_key="k", client=NeverCalled()).transcribe(silent)
        assert False, "expected SpeechError"
    except SpeechError as exc:
        assert "silent" in str(exc)


def test_public_spending_cap(monkeypatch):
    monkeypatch.setattr(webapp, "MAX_TURNS_PER_HOUR_PER_IP", 2)
    monkeypatch.setattr(webapp, "_turns_by_ip", {})
    monkeypatch.setattr(webapp, "_turns_today", [])
    assert client.post("/api/turn", data={"text": "عندي عرس"}).status_code == 200
    assert client.post("/api/turn", data={"text": "عندي عرس"}).status_code == 200
    third = client.post("/api/turn", data={"text": "عندي عرس"})
    assert third.status_code == 429 and "too many requests" in third.json()["error"]
    # the header set by a reverse proxy identifies the visitor
    assert client.post("/api/turn", data={"text": "عندي عرس"}, headers={"x-forwarded-for": "203.0.113.9"}).status_code == 200
