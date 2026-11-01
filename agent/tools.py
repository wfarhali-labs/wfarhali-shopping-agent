"""Tool definitions given to the model (OpenAI-compatible function calling, as used by Meta Model API)."""
from __future__ import annotations

TERMINAL_TOOLS = {"ask_customer", "propose_basket"}


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


_ITEM = {"type": "object", "additionalProperties": False, "required": ["need", "search_keywords"], "properties": {
    "need": {"type": "string", "description": "Short English label of one product the customer wants, e.g. 'white sneakers'."},
    "search_keywords": {"type": "string", "description": "2-3 short FRENCH words: product type + colour/key feature, e.g. 'robe rouge', 'baskets blanches'. No 'soirée', 'femme', 'élégante': long queries return worse results."},
    "size": {"type": "string", "description": "Size if given (EU shoe size, S/M/L...), else empty."},
    "color": {"type": "string", "description": "Colour in English if given, else empty."}}}

TOOLS: list[dict] = [
    _fn("record_understanding",
        "ALWAYS call first: what the customer asked, in a structured form shown to them. The catalogue is searched at once with each item's search_keywords and the results are returned.",
        {"items": {"type": "array", "items": _ITEM, "description": "One entry per distinct product requested."},
         "budget_dzd": {"type": ["integer", "null"], "description": "Total budget converted to Algerian dinars (DZD), null if none. Algerians count in centimes: '300 alf' = 3000 DZD, 'melyoun' = 10000 DZD, 'melyoun w nos' = 15000 DZD; '12000 da' = 12000 DZD."},
         "wilaya": {"type": "string", "description": "Delivery wilaya (Algerian province) if mentioned, else empty."},
         "summary_darija": {"type": "string", "description": "One short line in Algerian Darija (Arabic script) of what you understood."},
         "summary_en": {"type": "string", "description": "The same line in English, for non-Arabic readers."}},
        ["items", "budget_dzd", "wilaya", "summary_darija", "summary_en"]),
    _fn("search_catalogue",
        "Search the catalogue AGAIN for ONE need with different French keywords, only when the results returned by record_understanding were empty or irrelevant. Results carry an estimated total price in DZD (fees included).",
        {"need": {"type": "string", "description": "The need label from record_understanding."},
         "query": {"type": "string", "description": "French keywords (the catalogue is in French)."}},
        ["need", "query"]),
    _fn("plan_basket",
        "Pick one product per need so the basket fits the budget. Exact arithmetic is done by this tool, never by you. Call it again with exclude_ids when the customer rejects a product.",
        {"budget_dzd": {"type": ["integer", "null"]},
         "needs": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["need", "candidate_ids"],
                   "properties": {"need": {"type": "string"},
                                  "candidate_ids": {"type": "array", "items": {"type": "string"},
                                                    "description": "Product ids from search results, best match first; drop irrelevant ones."}}}},
         "exclude_ids": {"type": "array", "items": {"type": "string"},
                         "description": "Ids of products the customer rejected in this conversation (never propose them again). [] if none."}},
        ["budget_dzd", "needs", "exclude_ids"]),
    _fn("ask_customer",
        "Ask ONE short clarifying question when the request cannot be fulfilled as is (no product named, nothing found, ambiguous budget...). Ends your turn.",
        {"question_darija": {"type": "string"}, "question_en": {"type": "string"},
         "options": {"type": "array", "items": {"type": "string"}, "maxItems": 4,
                     "description": "2-4 short answers the customer can tap, in Darija (e.g. 'روبة', 'صباط', '3000 دج'). [] when a free answer is needed."}},
        ["question_darija", "question_en", "options"]),
    _fn("propose_basket",
        "Present the last plan to the customer. Ends your turn. The customer confirms before anything is sent.",
        {"message_darija": {"type": "string", "description": "Short friendly message in Darija about the proposal."},
         "message_en": {"type": "string", "description": "The same message in English."}},
        ["message_darija", "message_en"]),
]

SYSTEM_PROMPT = """You are the shopping agent of Wfarhali, a service that buys products from international stores for customers in Algeria and delivers them.
Customers write or speak in Algerian Arabic (Darija), Modern Standard Arabic, French or Arabizi, and may send a photo of a product.

Work with tools, step by step:
1. Call record_understanding first: every product they want (one item each) with FRENCH search keywords (the catalogue titles are French), sizes, colours, the total budget in DZD and the wilaya. If a photo is attached, describe the product in it as an item. Its result includes the catalogue search results for each item.
2. Only if a search returned nothing relevant, call search_catalogue for that need with other French keywords.
3. Call plan_basket with the relevant candidate ids per need, best first, and the budget. Never add prices yourself. Results carry requested_color yes/no when a colour was asked: put the "yes" ones first and leave out the "no" ones; if none says "yes", call search_catalogue once with other words (e.g. 'robe rouge longue'), and if still none, propose the closest and say plainly it is not the exact colour.
4. Call propose_basket. If the plan is over budget, say so honestly and by how much.
If no product can be identified, or a search finds nothing relevant, call ask_customer with ONE short question instead. Whenever the answer can be a choice (which product, which colour, which of two amounts), give 2-4 short tappable answers in options.

Money: Algerians usually count in centimes (100 centimes = 1 DZD). "alf"/"ألف" = 1000 centimes = 10 DZD, "melyoun"/"مليون" = 10000 DZD. So "300 alf" = 3000 DZD, "melyoun w nos" = 15000 DZD, "5 mlayen" = 50000 DZD. "da"/"دج"/"dinar" means dinars as written ("12000 da" = 12000 DZD); a bare number of 1000 or more is dinars. Put the converted budget in budget_dzd and repeat it in DZD in summary_darija so the customer can correct it. If the reading is unclear, or the budget would be under 1000 DZD, call ask_customer with the two possible amounts instead of guessing.

Photo: when a photo is attached, record_understanding also returns "photo": for each item, how many matches SAM 3.1 found in the photo for that item name. 0 matches means your reading of the photo is probably wrong: look again, and if still unsure call ask_customer. 2 or more matches means several such items are in the photo: call ask_customer to learn which one (colour, position), unless the customer clearly wants all of them. 1 match: continue; the customer is shown the cut-out.

Swap: when the customer rejects a proposed product (a message starting with "بدّل"), call plan_basket again with the same needs and budget, listing the rejected id (and any rejected earlier) in exclude_ids, keep the other products, then propose_basket. If no other candidate exists for that need, call search_catalogue once with different keywords first.

Rules: prices come only from tool results; they are estimates and Wfarhali's team confirms the final price. Do not talk about delivery costs or conditions; the team handles that.
Never claim an order was placed: the customer confirms in the app. Write Darija in Arabic script, short and warm, like a good shop assistant: no technical words, no repeating what the tools did. Always give the English line too."""
