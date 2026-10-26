"""Offline stand-in for Muse Spark: same tool-calling protocol, deterministic decisions.

It lets the agent loop, the tools, the planner and the UI run end to end with no API key and no cost.
Its "understanding" is the small rule set in darija.py; it cannot see photos.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from . import darija
from .llm import ModelTurn, ToolCall


def _since_last_user(messages: list[dict]) -> tuple[list[dict], dict | None]:
    for index in range(len(messages) - 1, -1, -1):
        if messages[index]["role"] == "user":
            return messages[index + 1:], messages[index]
    return messages, None


def _user_text(messages: list[dict]) -> tuple[str, bool]:
    """All user text so far (a clarification answer completes the first request) and whether the last turn has a photo."""
    texts, photo = [], False
    for message in messages:
        if message["role"] != "user":
            continue
        content = message["content"]
        if isinstance(content, str):
            texts.append(content)
        else:
            texts += [part.get("text", "") for part in content if part.get("type") == "text"]
            photo = any(part.get("type") == "image_url" for part in content)
    return " و ".join(t for t in texts if t), photo


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

        if "record_understanding" not in done:
            text, photo = _user_text(messages)
            request = darija.parse(text)
            if not request.items:
                if photo:
                    return call("ask_customer", question_darija="شفت الصورة! واش هو المنتج اللي حاب نلقالك؟ مثلا: صباط أبيض مقاس 40",
                                question_en="I got the photo! Which product should I find? e.g. white sneakers size 40")
                return call("ask_customer", question_darija="واش حاب تشري؟ قولّي المنتج، المقاس والميزانية.",
                            question_en="What would you like to buy? Tell me the product, size and budget.")
            summary_darija, summary_en = request.summaries()
            return call("record_understanding",
                        items=[{"need": i.need, "search_keywords": i.search_keywords, "size": i.size, "color": i.color} for i in request.items],
                        budget_dzd=request.budget_dzd, wilaya=request.wilaya, summary_darija=summary_darija, summary_en=summary_en)
        understanding = next(args for name, args in calls.values() if name == "record_understanding")
        searched = {args["need"] for name, args in calls.values() if name == "search_catalogue"}
        for item in understanding["items"]:
            if item["need"] not in searched:
                return call("search_catalogue", need=item["need"], query=item["search_keywords"])
        if "plan_basket" not in done:
            needs = []
            for call_id, (name, args) in calls.items():
                if name == "search_catalogue":
                    found = results.get(call_id, {}).get("products", [])
                    if not found:
                        return call("ask_customer", question_darija=f"ما لقيتش «{args['query']}». تقدر توصفلي المنتج بطريقة أخرى؟",
                                    question_en=f"I found nothing for '{args['query']}'. Could you describe it differently?")
                    needs.append({"need": args["need"], "candidate_ids": [p["id"] for p in found]})
            return call("plan_basket", budget_dzd=understanding.get("budget_dzd"), needs=needs)
        plan = next(results[cid] for cid, (name, _) in calls.items() if name == "plan_basket")
        if plan.get("within_budget", True):
            return call("propose_basket", message_darija="هذا أحسن اقتراح في حدود ميزانيتك. أكّد باش نبعثو طلب السعر.",
                        message_en="Here is the best proposal within your budget. Confirm to send the price request.")
        return call("propose_basket",
                    message_darija=f"أرخص اختيار يفوت الميزانية بـ {plan['over_by_dzd']:,} دج. تحب نبدّلو منتج ولا نزيدو في الميزانية؟".replace(",", " "),
                    message_en=f"The cheapest option is {plan['over_by_dzd']:,} DZD over budget. Swap a product or raise the budget?")
