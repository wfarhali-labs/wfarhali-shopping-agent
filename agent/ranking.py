"""Re-rank catalogue results for one need before the model sees them (deterministic, no model cost).

The partner catalogue answers a keyword query with dozens of products in no useful order; a request for a
red dress gets mostly non-red dresses first. Here each product is scored on the words the agent searched
for and on the requested colour, so the model and the planner see the best matches first.
"""
from __future__ import annotations

import re

from .catalogue import Product

# requested colour (English, as the model records it) -> words that mean it in French product titles
COLOR_WORDS = {
    "red": ["rouge"], "white": ["blanc", "blanche", "blancs", "blanches"], "black": ["noir", "noire", "noirs", "noires"],
    "blue": ["bleu", "bleue", "marine"], "green": ["vert", "verte"], "pink": ["rose"], "beige": ["beige", "crème"],
    "yellow": ["jaune"], "brown": ["marron", "brun", "brune"], "grey": ["gris", "grise"], "gray": ["gris", "grise"],
    "purple": ["violet", "violette", "mauve"], "orange": ["orange"], "gold": ["doré", "dorée", "or"], "silver": ["argent", "argenté"],
}
_ALL_COLOR_WORDS = {w for words in COLOR_WORDS.values() for w in words}
_WORD = re.compile(r"[\w'-]+", re.UNICODE)


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "") if len(w) > 2}


def requested_color_words(color: str) -> set[str]:
    key = (color or "").strip().lower()
    for name, words in COLOR_WORDS.items():
        if key == name or key.startswith(name):
            return set(words)
    return set()


def color_matches(product: Product, color: str) -> bool | None:
    """True/False when a colour was requested and the title says something about colour, None when unknown."""
    wanted = requested_color_words(color)
    if not wanted:
        return None
    words = _words(product.title + " " + (product.details or ""))
    if words & wanted:
        return True
    return False if words & _ALL_COLOR_WORDS else None


def rank(products: list[Product], query: str, color: str = "") -> list[Product]:
    """Best matches first: requested colour present, then the query words found in the title; stable otherwise."""
    query_words = _words(query) - _ALL_COLOR_WORDS
    scored = []
    for position, product in enumerate(products):
        words = _words(product.title + " " + (product.details or ""))
        score = len(query_words & words)
        match = color_matches(product, color)
        if match is True:
            score += 3
        elif match is False:
            score -= 2
        scored.append((-score, position, product))
    scored.sort(key=lambda entry: (entry[0], entry[1]))
    return [product for _, _, product in scored]
