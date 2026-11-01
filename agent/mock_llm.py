"""Offline stand-in for Muse Spark: same tool-calling protocol, deterministic decisions.

It lets the agent loop, the tools, the planner and the UI run end to end with no API key and no cost.
Its "understanding" is the small rule set in darija.py; it cannot see photos.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from . import darija
from .llm import ModelTurn, ToolCall


def _since_last_user(messages: list[dict]) -> tuple[list[dict], dict | None]:
    for index in range(len(messages) - 1, -1, -1):
        if messages[index]["role"] == "user":
            return messages[index + 1:], messages[index]
    return messages, None


SWAP = re.compile(r"^\s*بدّل|\(id ([^)]+)\)")


def _user_text(messages: list[dict]) -> tuple[str, bool, set[str]]:
    """All user text so far (a clarification answer completes the first request), whether the last turn has a photo,
    and the ids of products the customer rejected with the swap button (those messages are not part of the request)."""
    texts, photo, rejected = [], False, set()
    for message in messages:
        if message["role"] != "user":
            continue
        content = message["content"]
        parts = [content] if isinstance(content, str) else [part.get("text", "") for part in content if part.get("type") == "text"]
        if not isinstance(content, str):
            photo = any(part.get("type") == "image_url" for part in content)
        for text in parts:
            if text.strip().startswith("بدّل"):
                rejected |= {m for m in re.findall(r"\(id ([^)]+)\)", text)}
            elif text:
                texts.append(text)
    return " و ".join(texts), photo, rejected


@dataclass
class MockChatModel:
    name: str = "mock"

    def complete(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        recent, _ = _since_last_user(messages)
        calls = {}
        results = {}
        for message in recent:
            for call in message.get("tool_calls") or []:
                calls[call["id"]] = (call["function"]["name"], json.loads(call["function"]["arguments"]))
            if message["role"] == "tool":
                results[message["tool_call_id"]] = json.loads(message["content"])
        done = [name for name, _ in calls.values()]

        def call(name, **arguments):
            return ModelTurn(tool_calls=[ToolCall(id=f"mock_{len(calls) + 1}", name=name, arguments=arguments)])

        text, photo, rejected = _user_text(messages)
        if "record_understanding" not in done:
            request = darija.parse(text)
            if not request.items:
                if photo:
                    return call("ask_customer", question_darija="شفت الصورة! واش هو المنتج اللي حاب نلقالك؟ مثلا: صباط أبيض مقاس 40",
                                question_en="I got the photo! Which product should I find? e.g. white sneakers size 40", options=[])
                return call("ask_customer", question_darija="واش حاب تشري؟ قولّي المنتج، المقاس والميزانية.",
                            question_en="What would you like to buy? Tell me the product, size and budget.",
                            options=["روبة سهرة بـ مليون و200", "صباط أبيض مقاس 40", "ساك لمرا أسود"])
            summary_darija, summary_en = request.summaries()
            return call("record_understanding",
                        items=[{"need": i.need, "search_keywords": i.search_keywords, "size": i.size, "color": i.color} for i in request.items],
                        budget_dzd=request.budget_dzd, summary_darija=summary_darija, summary_en=summary_en)
        understanding_id, understanding = next((cid, args) for cid, (name, args) in calls.items() if name == "record_understanding")
        if "plan_basket" not in done:
            # record_understanding already searched the catalogue for every item; its result carries the products
            searches = results.get(understanding_id, {}).get("searches", [])
            needs = []
            for search in searches:
                found = search.get("products", [])
                if not found:
                    return call("ask_customer", question_darija=f"ما لقيتش «{search['query']}». تقدر توصفلي المنتج بطريقة أخرى؟",
                                question_en=f"I found nothing for '{search['query']}'. Could you describe it differently?", options=[])
                needs.append({"need": search["need"], "candidate_ids": [p["id"] for p in found if p["id"] not in rejected]})
            return call("plan_basket", budget_dzd=understanding.get("budget_dzd"), needs=needs, exclude_ids=sorted(rejected))
        plan = next(results[cid] for cid, (name, _) in calls.items() if name == "plan_basket")
        if plan.get("within_budget", True):
            return call("propose_basket", message_darija="هذا أحسن اقتراح في حدود ميزانيتك. أكّد باش نبعثو طلب السعر.",
                        message_en="Here is the best proposal within your budget. Confirm to send the price request.")
        return call("propose_basket",
                    message_darija=f"أرخص اختيار يفوت الميزانية بـ {plan['over_by_dzd']:,} دج. تحب نبدّلو منتج ولا نزيدو في الميزانية؟".replace(",", " "),
                    message_en=f"The cheapest option is {plan['over_by_dzd']:,} DZD over budget. Swap a product or raise the budget?")
