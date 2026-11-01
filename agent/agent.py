"""The agent loop: the model decides, the tools act, every step is recorded for the customer to see."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .catalogue import Catalogue, Product
from .llm import ChatModel, ModelError, ModelTurn
from .planner import plan_basket
from .segment import SegmentError, Segmenter, crop_data_url
from .tools import SYSTEM_PROMPT, TERMINAL_TOOLS, TOOLS

STEP_LABELS = {  # what the customer sees while the agent works (Darija, English)
    "record_understanding": ("فهمت طلبك", "Understood your request"),
    "locate_in_photo": ("حدّدت المنتج في الصورة", "Located the item in the photo"),
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
    products: dict = field(default_factory=dict)       # products seen so far (id -> Product), to continue the next turn

    def public(self) -> dict:
        return {"status": self.status, "steps": [s.__dict__ for s in self.steps], "understanding": self.understanding,
                "proposal": self.proposal, "question": self.question, "error": self.error}


class ShoppingAgent:
    def __init__(self, model: ChatModel, catalogue: Catalogue, max_steps: int = 10, segmenter: Segmenter | None = None):
        self.model, self.catalogue, self.max_steps, self.segmenter = model, catalogue, max_steps, segmenter

    @staticmethod
    def user_message(text: str = "", image_data_url: str | None = None) -> dict:
        if not image_data_url:
            return {"role": "user", "content": text}
        parts = [{"type": "text", "text": text or "Find this product for me."}]
        parts.append({"type": "image_url", "image_url": {"url": image_data_url}})
        return {"role": "user", "content": parts}

    def run(self, history: list[dict] | None, text: str = "", image_data_url: str | None = None, *,
            products: dict[str, Product] | None = None) -> TurnResult:
        """One customer turn. `history` and `products` come from the previous TurnResult to continue a conversation."""
        messages = list(history or []) or [{"role": "developer", "content": SYSTEM_PROMPT}]
        messages.append(self.user_message(text, image_data_url))
        steps: list[Step] = []
        state = {"products": dict(products or {}), "understanding": None, "plan": None, "photo": image_data_url}

        def done(status, **kw):
            return TurnResult(status, steps, messages, state["understanding"], products=state["products"], **kw)

        for _ in range(self.max_steps):
            try:
                turn = self.model.complete(messages, TOOLS)
            except ModelError as exc:
                return done("error", error=str(exc))
            messages.append(turn.as_message())
            if not turn.tool_calls:   # plain text: treat it as a question to the customer
                question = {"question_darija": turn.content, "question_en": ""}
                steps.append(Step("ask_customer", *STEP_LABELS["ask_customer"], question))
                return done("question", question=question)
            for call in turn.tool_calls:
                result, step = self._execute(call.name, call.arguments, state)
                steps.append(step)
                steps.extend(state.pop("extra_steps", []))   # searches run on the agent's own initiative
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)})
                if call.name == "ask_customer" and step.ok:
                    return done("question", question=result)
                if call.name == "propose_basket" and step.ok:
                    return done("proposal", proposal=result)
        return done("error", error="the agent did not finish in time")

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
        extra_steps = []
        # With a photo: ask SAM 3.1 where each item is, to check the model's reading and show the customer the cut-out.
        photo_check = self._locate_items(items, state, extra_steps) if state.get("photo") and self.segmenter else None
        # Search the catalogue for every item right away (in parallel: the live catalogue takes seconds per query).
        searches = []
        to_search = [item for item in items if item["search_keywords"].strip()]
        with ThreadPoolExecutor(max_workers=max(1, min(4, len(to_search)))) as pool:
            found = list(pool.map(lambda item: self.catalogue.search(item["search_keywords"]), to_search))
        for item, products in zip(to_search, found):
            result, detail = self._index(item["need"], item["search_keywords"], products, state)
            searches.append(result)
            extra_steps.append(Step("search_catalogue", *STEP_LABELS["search_catalogue"], detail))
        state["extra_steps"] = extra_steps
        result = {"recorded": True, "searches": searches}
        if photo_check is not None:
            result["photo"] = photo_check
        state["photo"] = None                                 # one check per photo
        return result, understanding

    def _locate_items(self, items: list[dict], state: dict, extra_steps: list) -> dict:
        """SAM 3.1 per item: number of matches in the photo (for the model) and the cut-outs (for the customer)."""
        report = {}

        def locate(item):
            try:
                return self.segmenter.locate(state["photo"], item["need"])
            except SegmentError as exc:
                return exc
        with ThreadPoolExecutor(max_workers=max(1, min(4, len(items)))) as pool:
            results = list(pool.map(locate, items))
        for item, boxes in zip(items, results):
            concept = item["need"]
            if isinstance(boxes, SegmentError):
                extra_steps.append(Step("locate_in_photo", *STEP_LABELS["locate_in_photo"], {"need": concept, "error": str(boxes)}, ok=False))
                continue
            crops = [c for c in (crop_data_url(state["photo"], box) for box in boxes[:3]) if c]
            report[concept] = {"matches": len(boxes)}
            extra_steps.append(Step("locate_in_photo", *STEP_LABELS["locate_in_photo"],
                                    {"need": concept, "count": len(boxes), "boxes": [b.public() for b in boxes], "thumbnails": crops}))
        return report

    def _tool_search_catalogue(self, args, state):
        need, query = str(args["need"]), str(args["query"]).strip()
        if not query:
            raise ValueError("empty query")
        return self._search(need, query, state)

    def _search(self, need: str, query: str, state: dict) -> tuple[dict, dict]:
        return self._index(need, query, self.catalogue.search(query), state)

    def _index(self, need: str, query: str, found: list[Product], state: dict) -> tuple[dict, dict]:
        for product in found:
            state["products"][product.id] = product
        # The model only needs what it decides with; links and images stay server-side and reach the customer in the proposal.
        for_model = [{"id": p.id, "title": p.title[:90], "store": p.store, "price_dzd": p.price_dzd, "category": p.category} for p in found]
        thumbnails = [p.image_url for p in found[:3] if p.image_url]
        return {"need": need, "query": query, "products": for_model}, {"need": need, "query": query, "count": len(found),
                                                                        "thumbnails": thumbnails}

    def _tool_plan_basket(self, args, state):
        excluded = {str(pid) for pid in args.get("exclude_ids") or []}       # products the customer rejected ("بدّل")
        needs = {}
        for entry in args["needs"]:
            ids = [str(pid) for pid in entry["candidate_ids"] if str(pid) in state["products"] and str(pid) not in excluded]
            needs[str(entry["need"])] = [(pid, state["products"][pid].price_dzd) for pid in ids]
        budget = args.get("budget_dzd")
        plan = plan_basket(needs, int(budget) if budget else None)
        state["plan"] = plan
        return plan.public(), plan.public()

    def _tool_ask_customer(self, args, state):
        options = [str(o).strip() for o in (args.get("options") or []) if str(o).strip()][:4]
        question = {"question_darija": str(args["question_darija"]), "question_en": str(args.get("question_en") or ""), "options": options}
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
