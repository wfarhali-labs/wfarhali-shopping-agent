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

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agent import catalogue as catalogue_module
from agent import llm as llm_module
from agent import segment as segment_module
from agent import speech as speech_module
from agent.agent import ShoppingAgent
from agent.config import Settings

ROOT = Path(__file__).resolve().parent
MAX_IMAGE_BYTES = 6 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
SESSION_TTL = 3600
MAX_SESSIONS = 500
# Spending guard for a public URL (every turn costs API money): per visitor per hour, and for the whole app per day.
MAX_TURNS_PER_HOUR_PER_IP = int(os.environ.get("WFAGENT_MAX_TURNS_PER_HOUR_PER_IP", "30") or 30)
MAX_TURNS_PER_DAY = int(os.environ.get("WFAGENT_MAX_TURNS_PER_DAY", "400") or 400)
_turns_by_ip: dict[str, list[float]] = {}
_turns_today: list[float] = []


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[0].strip() if forwarded else None) or (request.client.host if request.client else "?")


def _allow_turn(ip: str) -> bool:
    now = time.time()
    _turns_today[:] = [t for t in _turns_today if now - t < 86400]
    recent = _turns_by_ip[ip] = [t for t in _turns_by_ip.get(ip, []) if now - t < 3600]
    if len(_turns_today) >= MAX_TURNS_PER_DAY or len(recent) >= MAX_TURNS_PER_HOUR_PER_IP:
        return False
    recent.append(now)
    _turns_today.append(now)
    for key in [k for k, v in _turns_by_ip.items() if not v]:
        _turns_by_ip.pop(key, None)
    return True


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
agent = ShoppingAgent(llm_module.from_settings(settings), catalogue_module.from_settings(settings), settings.max_steps,
                      segmenter=segment_module.from_settings(settings))
transcriber = speech_module.from_settings(settings)
sessions: "OrderedDict[str, tuple[float, list[dict], dict]]" = OrderedDict()   # in memory (seen, messages, products): a demo, not a shop backend

app = FastAPI(title="Wfarhali shopping agent", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def no_stale_assets(request: Request, call_next):
    """Browsers must re-check the page and its assets on every visit, so an update never shows half old, half new."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "model": agent.model.name, "catalogue": agent.catalogue.name, "speech": transcriber.name,
            "segment": agent.segmenter.name if agent.segmenter else "off", "whatsapp": settings.whatsapp,
            "model_id": settings.model, "base_url": settings.meta_base_url, "key_set": bool(settings.model_api_key),
            "key_format_ok": settings.model_api_key.startswith("LLM_") and len(settings.model_api_key) == 48}


@app.get("/api/selftest")
def selftest(request: Request):
    """One tiny real call to the configured model from this server, to diagnose a deployment (costs a fraction of a cent)."""
    if not _allow_turn(_client_ip(request)):
        return JSONResponse({"error": "too many requests"}, status_code=429)
    import httpx
    body = {"model": settings.model, "messages": [{"role": "user", "content": "Say OK"}], "max_completion_tokens": 20, "reasoning_effort": "low"}
    try:
        tries = max(1, min(5, int(request.query_params.get("n", "1") or 1)))
        statuses = []
        for _ in range(tries):                              # several tiny calls show whether a failure is intermittent
            r = httpx.post(f"{settings.meta_base_url}/chat/completions", json=body, timeout=60,
                           headers={"Authorization": f"Bearer {settings.model_api_key}"})
            statuses.append(r.status_code)
        try:
            egress = httpx.get("https://api.ipify.org", timeout=10).text.strip()[:45]
        except Exception:
            egress = "unknown"
        try:                                                   # which models Meta offers to this server (depends on where it runs)
            listing = httpx.get(f"{settings.meta_base_url}/models", timeout=30, headers={"Authorization": f"Bearer {settings.model_api_key}"})
            models = sorted(m.get("id", "") for m in listing.json().get("data", [])) if listing.status_code == 200 else f"HTTP {listing.status_code}"
        except Exception as exc:
            models = f"{type(exc).__name__}"
        return {"model": settings.model, "base_url": settings.meta_base_url, "http_status": r.status_code, "statuses": statuses,
                "request_id": r.headers.get("x-request-id"), "body": r.text[:400], "egress_ip": egress, "models_visible": models}
    except Exception as exc:                                   # network failure: show it instead of a 500
        return {"model": settings.model, "base_url": settings.meta_base_url, "error": f"{type(exc).__name__}: {exc}"[:300]}


def _history(session_id: str) -> tuple[list[dict] | None, dict]:
    now = time.time()
    for key in [k for k, (seen, _, _) in sessions.items() if now - seen > SESSION_TTL]:
        sessions.pop(key, None)
    entry = sessions.get(session_id)
    return (entry[1], entry[2]) if entry else (None, {})


def _store(session_id: str, messages: list[dict], products: dict) -> None:
    sessions[session_id] = (time.time(), messages, products)
    sessions.move_to_end(session_id)
    while len(sessions) > MAX_SESSIONS:
        sessions.popitem(last=False)


@app.post("/api/turn")
async def turn(request: Request, text: str = Form(""), session_id: str = Form(""), audio: UploadFile | None = File(None),
               image: UploadFile | None = File(None)):
    if not _allow_turn(_client_ip(request)):
        return JSONResponse({"status": "error", "error": "too many requests: please try again later"}, status_code=429)
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
    history, products = _history(session_id)
    result = agent.run(history, text, image_url, products=products)
    _store(session_id, result.messages, result.products)
    return {"session_id": session_id, "transcript": transcript, **result.public()}
