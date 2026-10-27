"""Settings from the environment (a .env file is read by web/app.py when present)."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    llm: str = "mock"                      # mock | meta
    model_api_key: str = ""
    model: str = "muse-spark-1.3"
    meta_base_url: str = "https://api.meta.ai/v1"
    catalogue: str = "demo"                # demo | wfarhali
    wfarhali_base_url: str = "https://wfarhali.com"
    stt: str = "mock"                      # mock | meta
    segment: str = "mock"                  # mock | meta  (SAM 3.1: locate the product in the customer's photo)
    max_steps: int = 10

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            llm=env("WFAGENT_LLM", "mock").strip().lower() or "mock",
            model_api_key=env("MODEL_API_KEY", "").strip(),
            model=env("WFAGENT_MODEL", "muse-spark-1.3").strip() or "muse-spark-1.3",
            meta_base_url=env("META_BASE_URL", "https://api.meta.ai/v1").strip().rstrip("/"),
            catalogue=env("WFAGENT_CATALOGUE", "demo").strip().lower() or "demo",
            wfarhali_base_url=env("WFARHALI_BASE_URL", "https://wfarhali.com").strip().rstrip("/"),
            stt=env("WFAGENT_STT", "mock").strip().lower() or "mock",
            segment=env("WFAGENT_SEGMENT", "mock").strip().lower() or "mock",
            max_steps=int(env("WFAGENT_MAX_STEPS", "10") or 10),
        )
