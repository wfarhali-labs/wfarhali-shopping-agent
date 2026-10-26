"""The agent loop: the model decides, the tools act, every step is recorded for the customer to see."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .catalogue import Catalogue, Product
from .llm import ChatModel, ModelError, ModelTurn
from .planner import plan_basket
from .tools import SYSTEM_PROMPT, TERMINAL_TOOLS, TOOLS

STEP_LABELS = {  # what the customer sees while the agent works (Darija, English)
    "record_understanding": ("فهمت طلبك", "Understood your request"),
    "search_catalogue": ("يبحث في متاجر العالم", "Searching world stores"),
    "plan_basket": ("يخطط في حدود الميزانية", "Planning within budget"),
    "ask_customer": ("عندي سؤال", "One question"),
    "propose_basket": ("الاقتراح جاهز", "Proposal ready"),
}


@dataclass
class Step:
    tool: str
    label_darija: str
    label_en: str
    detail: dict = field(default_factory=dict)
    ok: bool = True


@dataclass
class TurnResult:
    status: str                                   # proposal | question | error
    steps: list[Step]
    messages: list[dict]                          # full conversation, to continue the next turn
    understanding: dict | None = None
    proposal: dict | None = None
    question: dict | None = None
    error: str = ""

    def public(self) -> dict:
        return {"status": self.status, "steps": [s.__dict__ for s in self.steps], "understanding": self.understanding,
                "proposal": self.proposal, "question": self.question, "error": self.error}


class ShoppingAgent:
    def __init__(self, model: ChatModel, catalogue: Catalogue, max_steps: int = 10):
        self.model, self.catalogue, self.max_steps = model, catalogue, max_steps

    @staticmethod
    def user_message(text: str = "", image_data_url: str | None = None) -> dict:
        if not image_data_url:
            return {"role": "user", "content": text}
        parts = [{"type": "text", "text": text or "Find this product for me."}]
        parts.append({"type": "image_url", "image_url": {"url": image_data_url}})
        return {"role": "user", "content": parts}

    def run(self, history: list[dict] | None, text: str = "", image_data_url: str | None = None) -> TurnResult:
        messages = list(history or []) or [{"role": "developer", "content": SYSTEM_PROMPT}]
        messages.append(self.user_message(text, image_data_url))
        steps: list[Step] = []
        state = {"products": {}, "understanding": None, "plan": None}
        for _ in range(self.max_steps):
            try:
                turn = self.model.complete(messages, TOOLS)
            except ModelError as exc:
                return TurnResult("error", steps, messages, error=str(exc))
            messages.append(turn.as_message())
            if not turn.tool_calls:   # plain text: treat it as a question to the customer
                question = {"question_darija": turn.content, "question_en": ""}
                steps.append(Step("ask_customer", *STEP_LABELS["ask_customer"], question))
                return TurnResult("question", steps, messages, state["understanding"], question=question)
            for call in turn.tool_calls:
                result, step = self._execute(call.name, call.arguments, state)
                steps.append(step)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)})
                if call.name == "ask_customer" and step.ok:
                    return TurnResult("question", steps, messages, state["understanding"], question=result)
                if call.name == "propose_basket" and step.ok:
                    return TurnResult("proposal", steps, messages, state["understanding"], proposal=result)
        return TurnResult("error", steps, messages, state["understanding"], error="the agent did not finish in time")

    # ---- tools ----
    def _execute(self, name: str, args: dict, state: dict) -> tuple[dict, Step]:
        label = STEP_LABELS.get(name, (name, name))
        try:
            handler = getattr(self, f"_tool_{name}")
        except AttributeError:
            return {"error": f"unknown tool {name}"}, Step(name, *label, {"error": "unknown tool"}, ok=False)
        try:
            result, detail = handler(args, state)
        except (KeyError, TypeError, ValueError) as exc:   # malformed arguments: tell the model, let it retry
            return {"error": f"invalid arguments: {exc}"}, Step(name, *label, {"error": str(exc)}, ok=False)
        ok = "error" not in result
        return result, Step(name, *label, detail, ok=ok)

    def _tool_record_understanding(self, args, state):
        items = [{"need": str(i["need"]), "search_keywords": str(i["search_keywords"]), "size": str(i.get("size") or ""),
                  "color": str(i.get("color") or "")} for i in args["items"]]
        budget = args.get("budget_dzd")
        understanding = {"items": items, "budget_dzd": int(budget) if budget else None, "wilaya": str(args.get("wilaya") or ""),
                         "summary_darija": str(args.get("summary_darija") or ""), "summary_en": str(args.get("summary_en") or "")}
        state["understanding"] = understanding
        return {"recorded": True}, understanding

    def _tool_search_catalogue(self, args, state):
        need, query = str(args["need"]), str(args["query"]).strip()
        if not query:
            raise ValueError("empty query")
        found: list[Product] = self.catalogue.search(query)
        for product in found:
            state["products"][product.id] = product
        public = [p.public() for p in found]
        return {"need": need, "products": public}, {"need": need, "query": query, "count": len(found),
                                                     "thumbnails": [p["image_url"] for p in public[:3] if p["image_url"]]}

    def _tool_plan_basket(self, args, state):
        needs = {}
        for entry in args["needs"]:
            ids = [str(pid) for pid in entry["candidate_ids"] if str(pid) in state["products"]]
            needs[str(entry["need"])] = [(pid, state["products"][pid].price_dzd) for pid in ids]
        budget = args.get("budget_dzd")
        plan = plan_basket(needs, int(budget) if budget else None)
        state["plan"] = plan
        return plan.public(), plan.public()

    def _tool_ask_customer(self, args, state):
        question = {"question_darija": str(args["question_darija"]), "question_en": str(args.get("question_en") or "")}
        return question, question

    def _tool_propose_basket(self, args, state):
        plan = state["plan"]
        if plan is None:
            return {"error": "call plan_basket first"}, {"error": "no plan"}
        items = [{"need": c.need, **state["products"][c.product_id].public()} for c in plan.choices]
        proposal = {"items": items, "total_dzd": plan.total_dzd, "budget_dzd": plan.budget_dzd, "within_budget": plan.within_budget,
                    "over_by_dzd": plan.over_by, "missing": list(plan.missing),
                    "message_darija": str(args["message_darija"]), "message_en": str(args.get("message_en") or ""),
                    "note_darija": "السعر تقديري، فريق وفّرهالي يأكد السعر النهائي. التوصيل داخل الجزائر غير محسوب.",
                    "note_en": "Estimated prices; Wfarhali's team confirms the final price. Delivery inside Algeria not included."}
        return proposal, {"items": len(items), "total_dzd": plan.total_dzd}
