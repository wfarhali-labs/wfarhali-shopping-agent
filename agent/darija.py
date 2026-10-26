"""A small rule-based reader of Darija shopping requests, used ONLY by the offline mock model.

It understands the demo sentences so the whole agent (tools, planner, UI) runs without any API.
The real understanding (any phrasing, photos) is done by Muse Spark through Meta Model API.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# (pattern, need in English, French keywords, Darija label)
PRODUCTS = [
    (r"صباط|سباط|صبابط|سبابط|صباطات|\bbaskets?\b|\bsneakers?\b|سبرديلة|سبادري", "sneakers", "baskets", "صباط"),
    (r"صندالة|صنادل|صندل|\bsandales?\b", "sandals", "sandales", "صنادل"),
    (r"روبة|روبه|روبات|فستان|\brobes?\b|\bdress\b", "dress", "robe", "روبة"),
    (r"ساك|صاك|حقيبة|شنطة|\bsac\b", "handbag", "sac à main", "ساك"),
    (r"ساعة|ساعه|مونطر|\bmontre\b|\bwatch\b", "watch", "montre", "ساعة"),
    (r"سروال|سراول|\bpantalon\b", "trousers", "pantalon", "سروال"),
    (r"كيتمان|سماعات|\bécouteurs\b|\bearbuds\b", "earbuds", "écouteurs sans fil", "سماعات"),
    (r"عطر|ريحة|\bparfum\b", "perfume", "parfum", "عطر"),
]
COLORS = [
    (r"أبيض|ابيض|بيضاء|بيضا|بيض|\bblanc\w*|\bwhite\b", "white", "blanc", "أبيض"),
    (r"أسود|اسود|كحل|كحلة|\bnoir\w*|\bblack\b", "black", "noir", "أسود"),
    (r"أحمر|احمر|حمرة|\brouge\b|\bred\b", "red", "rouge", "أحمر"),
]
MODIFIERS = [
    (r"صيف|صيفية|صيفي|\bété\b|\bsummer\b", "summer", "été", "صيفية"),
    (r"رجال|رجالي|للرجال|\bhomme\b|\bmen\b", "men", "homme", "رجالي"),
    (r"نسا|نساء|لمرا|للمرا|نسائي|نسائية|\bfemme\b|\bwomen\b", "women", "femme", "نسائي"),
]
WILAYAS = {
    "الجزائر": "Algiers", "دزاير": "Algiers", "alger": "Algiers", "وهران": "Oran", "oran": "Oran", "قسنطينة": "Constantine",
    "باتنة": "Batna", "batna": "Batna", "سطيف": "Sétif", "عنابة": "Annaba", "بجاية": "Béjaïa", "تيزي وزو": "Tizi Ouzou",
    "البليدة": "Blida", "تلمسان": "Tlemcen", "بسكرة": "Biskra", "ورقلة": "Ouargla", "الشلف": "Chlef", "سكيكدة": "Skikda",
    "جيجل": "Jijel", "المسيلة": "M'Sila", "بومرداس": "Boumerdès", "تيبازة": "Tipaza", "غرداية": "Ghardaïa", "مستغانم": "Mostaganem",
}
_AR_WILAYA = {"Algiers": "الجزائر", "Oran": "وهران", "Constantine": "قسنطينة", "Batna": "باتنة"}


@dataclass
class Item:
    need: str
    search_keywords: str
    size: str = ""
    color: str = ""
    label_darija: str = ""


@dataclass
class Request:
    items: list[Item]
    budget_dzd: int | None
    wilaya: str

    def summaries(self) -> tuple[str, str]:
        darija = " + ".join(item.label_darija for item in self.items)
        english = " + ".join(f"{item.need}{' size ' + item.size if item.size else ''}" for item in self.items)   # need already carries the colour
        if self.budget_dzd:
            darija += f"، الميزانية {self.budget_dzd:,} دج".replace(",", " ")
            english += f", budget {self.budget_dzd:,} DZD"
        if self.wilaya:
            darija += f"، التوصيل لـ{_AR_WILAYA.get(self.wilaya, self.wilaya)}"
            english += f", delivery to {self.wilaya}"
        return darija, english


def _find(table, text):
    for pattern, english, french, darija in table:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return english, french, darija
    return None


def parse(text: str) -> Request:
    text = (text or "").translate(_DIGITS)
    budget = None
    money = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ألف|الف|آلاف|alf|k\b)", text, flags=re.IGNORECASE)
    if money:
        budget = int(float(money.group(1).replace(",", ".")) * 1000)
    else:
        money = re.search(r"(\d[\d\s]{2,})\s*(?:دج|دينار|da\b|dzd\b)", text, flags=re.IGNORECASE)
        if money:
            budget = int(re.sub(r"\s", "", money.group(1)))
    wilaya = next((name for key, name in WILAYAS.items() if re.search(rf"(?:^|[\sلـ]){re.escape(key)}", text, flags=re.IGNORECASE)), "")
    segments = re.split(r"\s+و(?=\S)|\s+و\s+|,|،|\+|\bet\b|\band\b", text)
    items: list[Item] = []
    for segment in segments:
        product = _find(PRODUCTS, segment)
        if not product:
            continue
        need, french, darija = product
        color = _find(COLORS, segment)
        modifier = _find(MODIFIERS, segment)
        size = re.search(r"(?:مقاس|قياس|نمرة|pointure|taille|size)\s*(\d{2}|[smlx]{1,3})\b", segment, flags=re.IGNORECASE)
        keywords = [french] + ([color[1]] if color else []) + ([modifier[1]] if modifier else [])
        label = " ".join([darija] + ([color[2]] if color else []) + ([modifier[2]] if modifier else []) + ([f"مقاس {size.group(1)}"] if size else []))
        items.append(Item(need=" ".join(([color[0]] if color else []) + ([modifier[0]] if modifier else []) + [need]),
                          search_keywords=" ".join(keywords), size=size.group(1).upper() if size else "",
                          color=color[0] if color else "", label_darija=label))
    return Request(items=items, budget_dzd=budget, wilaya=wilaya)
