"""Product catalogues the agent can search.

- WfarhaliCatalogue: the live Wfarhali search API (https://wfarhali.com/api/live-search). It existed
  before the hackathon; it searches partner stores and returns, for each product, an estimated total
  in Algerian dinars computed by Wfarhali's own pricing system (closed source, not in this repository).
- DemoCatalogue: a small synthetic catalogue (data/demo_catalogue.json) so the agent runs offline,
  in tests and in demos without any network access.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

DATA = Path(__file__).resolve().parents[1] / "data"


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    store: str
    price_dzd: int | None          # estimated total for one unit, fees included; None = priced later by the team
    category: str = ""
    image_url: str | None = None
    product_url: str | None = None
    details: str = ""              # longer title / tags, used for ranking only

    def public(self) -> dict:
        return {"id": self.id, "title": self.title, "store": self.store, "price_dzd": self.price_dzd,
                "category": self.category, "image_url": self.image_url, "product_url": self.product_url}


class Catalogue(Protocol):
    name: str

    def search(self, query: str, limit: int = 6) -> list[Product]: ...


_WORD = re.compile(r"[\w'-]+", re.UNICODE)


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "") if len(w) > 1}


@dataclass
class DemoCatalogue:
    """Keyword match over data/demo_catalogue.json: most shared words first, then cheaper first."""
    path: Path = DATA / "demo_catalogue.json"
    name: str = "demo"
    _items: list[dict] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self._items = json.loads(Path(self.path).read_text(encoding="utf-8"))

    def search(self, query: str, limit: int = 6) -> list[Product]:
        wanted = _words(query)
        scored = []
        for row in self._items:
            words = _words(row["title"]) | {t.lower() for t in row.get("tags", [])}
            score = len(wanted & words)
            if score:
                scored.append((-score, row["price_dzd"], row))
        scored.sort(key=lambda entry: (entry[0], entry[1]))
        return [Product(id=row["id"], title=row["title"], store=row["store"], price_dzd=row["price_dzd"],
                        category=row.get("category", ""), image_url=row.get("image_url"), product_url=row.get("product_url"),
                        details=" ".join(row.get("tags", [])))
                for _, _, row in scored[:limit]]


@dataclass
class WfarhaliCatalogue:
    """Client of the public Wfarhali search endpoint; only its public JSON fields are used."""
    base_url: str = "https://wfarhali.com"
    timeout: float = 20.0
    name: str = "wfarhali"
    client: httpx.Client | None = None

    def search(self, query: str, limit: int = 6) -> list[Product]:
        client = self.client or httpx.Client(timeout=self.timeout, headers={"User-Agent": "wfarhali-shopping-agent"})
        try:
            response = client.get(f"{self.base_url}/api/live-search", params={"q": query})
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        finally:
            if self.client is None:
                client.close()
        if data.get("status") != "ok":
            return []
        products = []
        for row in data.get("results", [])[:limit]:
            estimate = row.get("estimate_dzd")
            products.append(Product(
                id=str(row.get("id")), title=str(row.get("title") or ""), store=str(row.get("source_store") or "").upper(),
                price_dzd=int(estimate) if isinstance(estimate, (int, float)) and estimate > 0 else None,
                category=str(row.get("pricing_category") or ""), image_url=row.get("image_url"), product_url=row.get("product_url"),
                details=str(row.get("full_title") or "")))
        return products


def from_settings(settings) -> Catalogue:
    if settings.catalogue == "wfarhali":
        return WfarhaliCatalogue(base_url=settings.wfarhali_base_url)
    return DemoCatalogue()
