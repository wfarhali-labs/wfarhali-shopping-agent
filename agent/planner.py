"""Pick one product per need so the basket fits the budget (deterministic, no model involved).

The model decides WHAT the customer needs and which candidates are relevant; this function does the
arithmetic, so totals are always exact. Preference: earlier candidates rank higher (the model / the
catalogue already ordered them by relevance).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

MAX_CANDIDATES = 6


@dataclass(frozen=True)
class Choice:
    need: str
    product_id: str
    price_dzd: int


@dataclass(frozen=True)
class Plan:
    choices: tuple[Choice, ...]
    total_dzd: int
    budget_dzd: int | None
    within_budget: bool
    missing: tuple[str, ...]           # needs with no priced candidate

    @property
    def over_by(self) -> int:
        return 0 if self.budget_dzd is None else max(0, self.total_dzd - self.budget_dzd)

    def public(self) -> dict:
        return {"choices": [c.__dict__ for c in self.choices], "total_dzd": self.total_dzd, "budget_dzd": self.budget_dzd,
                "within_budget": self.within_budget, "over_by_dzd": self.over_by, "missing": list(self.missing)}


def plan_basket(needs: dict[str, list[tuple[str, int | None]]], budget_dzd: int | None = None) -> Plan:
    """needs: {need label: [(product_id, price_dzd or None), ...] in preference order}."""
    options: dict[str, list[tuple[int, str, int]]] = {}
    missing = []
    for need, candidates in needs.items():
        priced = [(rank, pid, price) for rank, (pid, price) in enumerate(candidates[:MAX_CANDIDATES]) if isinstance(price, int) and price > 0]
        if priced:
            options[need] = priced
        else:
            missing.append(need)
    if not options:
        return Plan((), 0, budget_dzd, budget_dzd is None, tuple(missing))
    labels = list(options)
    best = None
    for combo in itertools.product(*(options[label] for label in labels)):
        total = sum(price for _, _, price in combo)
        rank_cost = sum(rank for rank, _, _ in combo)
        fits = budget_dzd is None or total <= budget_dzd
        # Fitting baskets first; among them the most relevant (lowest rank sum), then the cheapest.
        # When nothing fits: the cheapest basket, so the customer sees how far over it is.
        key = (0, rank_cost, total) if fits else (1, total, rank_cost)
        if best is None or key < best[0]:
            best = (key, combo, total, fits)
    _, combo, total, fits = best
    choices = tuple(Choice(label, pid, price) for label, (_, pid, price) in zip(labels, combo))
    return Plan(choices, total, budget_dzd, fits, tuple(missing))
