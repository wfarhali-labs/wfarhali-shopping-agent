"""Web app: one page (web/static) and one JSON endpoint for each customer turn.

Run:  uvicorn web.app:app --port 8000   (reads .env when present)
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
import time
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agent import catalogue as catalogue_module
from agent import llm as llm_module
from agent import speech as speech_module
from agent.agent import ShoppingAgent
from agent.config import Settings

ROOT = Path(__file__).resolve().parent
MAX_IMAGE_BYTES = 6 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
SESSION_TTL = 3600
MAX_SESSIONS = 500


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(ROOT.parent / ".env")
settings = Settings.from_env()
DEBUG_AUDIO_FILE = ROOT.parent / "last_voice.wav" if os.environ.get("WFAGENT_DEBUG_AUDIO", "").strip() == "1" else None
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
agent = ShoppingAgent(llm_module.from_settings(settings), catalogue_module.from_settings(settings), settings.max_steps)
transcriber = speech_module.from_settings(settings)
sessions: "OrderedDict[str, tuple[float, list[dict]]]" = OrderedDict()   # in memory: a demo, not a shop backend

app = FastAPI(title="Wfarhali shopping agent", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "model": agent.model.name, "catalogue": agent.catalogue.name, "speech": transcriber.name}


def _history(session_id: str) -> list[dict] | None:
    now = time.time()
    for key in [k for k, (seen, _) in sessions.items() if now - seen > SESSION_TTL]:
        sessions.pop(key, None)
    entry = sessions.get(session_id)
    return entry[1] if entry else None


def _store(session_id: str, messages: list[dict]) -> None:
    sessions[session_id] = (time.time(), messages)
    sessions.move_to_end(session_id)
    while len(sessions) > MAX_SESSIONS:
        sessions.popitem(last=False)


@app.post("/api/turn")
async def turn(text: str = Form(""), session_id: str = Form(""), audio: UploadFile | None = File(None),
               image: UploadFile | None = File(None)):
    text = text.strip()[:600]
    transcript = ""
    if audio is not None:
        wav = await audio.read()
        if DEBUG_AUDIO_FILE:                                 # WFAGENT_DEBUG_AUDIO=1: keep the last recording to listen to it
            DEBUG_AUDIO_FILE.write_bytes(wav)
        try:
            transcript = transcriber.transcribe(wav)
        except speech_module.SpeechError as exc:
            return JSONResponse({"status": "error", "error": f"voice: {exc}"}, status_code=422)
        if not transcript and not text:
            return JSONResponse({"status": "error", "error": "voice: nothing understood in the recording"}, status_code=422)
        text = (transcript + " " + text).strip()
    image_url = None
    if image is not None:
        data = await image.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "photo too large (6 MB max)")
        if image.content_type not in IMAGE_TYPES:
            raise HTTPException(415, "unsupported photo type")
        image_url = f"data:{image.content_type};base64,{base64.b64encode(data).decode()}"
    if not text and not image_url:
        raise HTTPException(422, "say, type or send a photo")
    session_id = session_id if session_id in sessions else secrets.token_urlsafe(12)
    result = agent.run(_history(session_id), text, image_url)
    _store(session_id, result.messages)
    return {"session_id": session_id, "transcript": transcript, **result.public()}
