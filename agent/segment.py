"""Locate the product in the customer's photo with SAM 3.1 (Meta Model API), or an offline stand-in.

The agent uses this to check its own reading of a photo: Muse Spark names the item it sees, SAM 3.1 is
asked for that noun phrase, and the matches come back as boxes. Zero matches means the reading is
probably wrong; several matches mean the customer has to say which one; one match is cut out of the photo
and shown to the customer as "this is what I understood".

SAM 3.1 is called through POST /v1/responses with an input_text (short noun phrase) and an input_image.
It answers with a special-token text: `<0f>` then, per object, `id<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|><|mask;...|>`.
Only the boxes are used here; masks are left encoded.
"""
from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

_BOX = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)\|>")
_DATA_URL = re.compile(r"^data:(image/[\w.+-]+);base64,(.+)$", re.DOTALL)
CROP_MAX_SIDE = 512
MAX_MATCHES = 4


class SegmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class Box:
    x1: int
    y1: int
    x2: int
    y2: int
    width: int                     # of the whole image, as the model saw it
    height: int

    def public(self) -> dict:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2, "width": self.width, "height": self.height}


class Segmenter(Protocol):
    name: str

    def locate(self, image_data_url: str, concept: str) -> list[Box]: ...


def parse_boxes(output_text: str) -> list[Box]:
    return [Box(*(int(v) for v in m.groups())) for m in _BOX.finditer(output_text or "")]


def decode_data_url(image_data_url: str) -> tuple[str, bytes]:
    match = _DATA_URL.match(image_data_url or "")
    if not match:
        raise SegmentError("photo must be a base64 data URL")
    return match.group(1), base64.b64decode(match.group(2))


def crop_data_url(image_data_url: str, box: Box) -> str | None:
    """Cut the box out of the photo and return it as a small JPEG data URL (None if the photo cannot be read)."""
    try:
        from PIL import Image, ImageOps
        _, raw = decode_data_url(image_data_url)
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:              # Pillow missing, corrupt photo...: the crop is a nicety, never a failure
        return None
    # Box coordinates are in the model's view of the image; scale them if the photo was resized.
    sx, sy = image.width / max(1, box.width), image.height / max(1, box.height)
    left, top = max(0, int(box.x1 * sx)), max(0, int(box.y1 * sy))
    right, bottom = min(image.width, int((box.x2 + 1) * sx)), min(image.height, int((box.y2 + 1) * sy))
    if right - left < 2 or bottom - top < 2:
        return None
    crop = image.crop((left, top, right, bottom))
    crop.thumbnail((CROP_MAX_SIDE, CROP_MAX_SIDE))
    out = io.BytesIO()
    crop.save(out, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


@dataclass
class MetaSegmenter:
    api_key: str
    base_url: str = "https://api.meta.ai/v1"
    model: str = "sam-3.1"
    timeout: float = 60.0
    client: httpx.Client | None = None
    name: str = "meta"

    def locate(self, image_data_url: str, concept: str) -> list[Box]:
        if not self.api_key:
            raise SegmentError("MODEL_API_KEY is not set")
        concept = " ".join((concept or "").split())[:60]
        if not concept:
            raise SegmentError("empty concept")
        body = {"model": self.model, "metadata": {"mask_encoding": "one_bit"},
                "input": [{"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": concept}, {"type": "input_image", "image_url": image_data_url}]}]}
        client = self.client or httpx.Client(timeout=self.timeout)
        try:
            response = client.post(f"{self.base_url}/responses", json=body, headers={"Authorization": f"Bearer {self.api_key}"})
        finally:
            if self.client is None:
                client.close()
        if response.status_code >= 400:
            raise SegmentError(f"SAM 3.1 {response.status_code}: {response.text[:200]}")
        data = response.json()
        text = data.get("output_text") or ""
        if not text:
            for item in data.get("output") or []:
                for block in item.get("content") or []:
                    if block.get("type") == "output_text":
                        text += block.get("text") or ""
        return parse_boxes(text)[:MAX_MATCHES]


@dataclass
class MockSegmenter:
    """Offline: one match in the middle of the photo, so the photo flow can be demonstrated without an API."""
    name: str = "mock"

    def locate(self, image_data_url: str, concept: str) -> list[Box]:
        try:
            from PIL import Image
            _, raw = decode_data_url(image_data_url)
            width, height = Image.open(io.BytesIO(raw)).size
        except Exception:
            width, height = 100, 100
        return [Box(width // 5, height // 5, width * 4 // 5, height * 4 // 5, width, height)]


def from_settings(settings) -> Segmenter:
    if settings.segment == "meta":
        return MetaSegmenter(api_key=settings.model_api_key, base_url=settings.meta_base_url)
    return MockSegmenter()
