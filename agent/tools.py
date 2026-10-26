"""Tool definitions given to the model (OpenAI-compatible function calling, as used by Meta Model API)."""
from __future__ import annotations

TERMINAL_TOOLS = {"ask_customer", "propose_basket"}


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


_ITEM = {"type": "object", "additionalProperties": False, "required": ["need", "search_keywords"], "properties": {
    "need": {"type": "string", "description": "Short English label of one product the customer wants, e.g. 'white sneakers'."},
    "search_keywords": {"type": "string", "description": "2-5 FRENCH catalogue keywords for this product, e.g. 'baskets blanches femme'."},
    "size": {"type": "string", "description": "Size if given (EU shoe size, S/M/L...), else empty."},
    "color": {"type": "string", "description": "Colour in English if given, else empty."}}}

TOOLS: list[dict] = [
    _fn("record_understanding",
        "ALWAYS call first: what the customer asked, in a structured form shown to them for transparency.",
        {"items": {"type": "array", "items": _ITEM, "description": "One entry per distinct product requested."},
         "budget_dzd": {"type": ["integer", "null"], "description": "Total budget in Algerian dinars, null if none. '15 alf' = 15000."},
         "wilaya": {"type": "string", "description": "Delivery wilaya (Algerian province) if mentioned, else empty."},
         "summary_darija": {"type": "string", "description": "One short line in Algerian Darija (Arabic script) of what you understood."},
         "summary_en": {"type": "string", "description": "The same line in English, for non-Arabic readers."}},
        ["items", "budget_dzd", "wilaya", "summary_darija", "summary_en"]),
    _fn("search_catalogue",
        "Search the partner-store catalogue for ONE need. Results carry an estimated total price in DZD (fees included).",
        {"need": {"type": "string", "description": "The need label from record_understanding."},
         "query": {"type": "string", "description": "French keywords (the catalogue is in French)."}},
        ["need", "query"]),
    _fn("plan_basket",
        "Pick one product per need so the basket fits the budget. Exact arithmetic is done by this tool, never by you.",
        {"budget_dzd": {"type": ["integer", "null"]},
         "needs": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["need", "candidate_ids"],
                   "properties": {"need": {"type": "string"},
                                  "candidate_ids": {"type": "array", "items": {"type": "string"},
                                                    "description": "Product ids from search results, best match first; drop irrelevant ones."}}}}},
        ["budget_dzd", "needs"]),
    _fn("ask_customer",
        "Ask ONE short clarifying question when the request cannot be fulfilled as is (no product named, nothing found...). Ends your turn.",
        {"question_darija": {"type": "string"}, "question_en": {"type": "string"}},
        ["question_darija", "question_en"]),
    _fn("propose_basket",
        "Present the last plan to the customer. Ends your turn. The customer confirms before anything is sent.",
        {"message_darija": {"type": "string", "description": "Short friendly message in Darija about the proposal."},
         "message_en": {"type": "string", "description": "The same message in English."}},
        ["message_darija", "message_en"]),
]

SYSTEM_PROMPT = """You are the shopping agent of Wfarhali, a service that buys products from international stores for customers in Algeria and delivers them.
Customers write or speak in Algerian Arabic (Darija), Modern Standard Arabic, French or Arabizi, and may send a photo of a product.

Work with tools, step by step:
1. Call record_understanding first: every product they want (one item each), sizes, colours, the total budget in DZD ("15 alf" = 15000) and the wilaya. If a photo is attached, describe the product in it as an item.
2. Call search_catalogue once per item, with FRENCH keywords (the catalogue titles are French).
3. Call plan_basket with the relevant candidate ids per need, best first, and the budget. Never add prices yourself.
4. Call propose_basket. If the plan is over budget, say so honestly and by how much.
If no product can be identified, or a search finds nothing relevant, call ask_customer with ONE short question instead.

Rules: prices come only from tool results; they are estimates and Wfarhali's team confirms the final price. Delivery inside Algeria is not included in the estimates.
Never claim an order was placed: the customer confirms in the app. Write Darija in Arabic script, short and warm. Always give the English line too."""
