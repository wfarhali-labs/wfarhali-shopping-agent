import json

import httpx
import pytest

from agent import darija
from agent.agent import ShoppingAgent
from agent.catalogue import DemoCatalogue
from agent.llm import MetaChatModel, ModelError, ModelTurn, ToolCall
from agent.mock_llm import MockChatModel

DEMO = "حاب صباط أبيض مقاس 40 وروبة صيف، الميزانية مليون ونص"


def agent():
    return ShoppingAgent(MockChatModel(), DemoCatalogue())


def test_darija_reader_understands_the_demo_sentence():
    request = darija.parse(DEMO)
    assert [i.need for i in request.items] == ["white sneakers", "summer dress"]
    assert request.items[0].size == "40" and request.items[0].search_keywords == "baskets blanc"
    assert request.budget_dzd == 15000
    assert darija.parse("ساعة لمرا بـ ٥٠٠ ألف").budget_dzd == 5000         # Arabic-Indic digits; "ألف" = 1000 centimes = 10 DZD
    assert darija.parse("روبة تاع خرجة بـ 300 ألف").budget_dzd == 3000
    assert darija.parse("ساك بـ مليون").budget_dzd == 10000 and darija.parse("ساك بـ 2 ملاين").budget_dzd == 20000
    assert darija.parse("baskets blanches et robe, 12000 da").budget_dzd == 12000


def test_full_turn_proposes_a_basket_within_budget():
    result = agent().run(None, DEMO)
    assert result.status == "proposal"
    assert [s.tool for s in result.steps] == ["record_understanding", "search_catalogue", "search_catalogue", "plan_basket", "propose_basket"]
    proposal = result.proposal
    assert proposal["within_budget"] and proposal["total_dzd"] <= 15000
    assert {i["need"] for i in proposal["items"]} == {"white sneakers", "summer dress"}
    assert result.understanding["summary_en"].startswith("white sneakers size 40 + summer dress")
    assert "الميزانية" in result.understanding["summary_darija"] and "التوصيل" not in result.understanding["summary_darija"]


def test_over_budget_is_said_honestly():
    result = agent().run(None, "صباط أسود وساعة رجالي بـ 800 ألف")        # 800 000 centimes = 8 000 DZD
    assert result.status == "proposal" and not result.proposal["within_budget"]
    assert result.proposal["over_by_dzd"] == result.proposal["total_dzd"] - 8000 > 0


def test_unclear_request_gets_one_question_then_continues():
    first = agent().run(None, "سلام، عندي عرس الجمعة")
    assert first.status == "question" and first.question["question_en"] and len(first.question["options"]) == 3
    second = agent().run(first.messages, "روبة سهرة بـ مليون و200", products=first.products)
    assert second.status == "proposal" and second.proposal["items"][0]["need"] == "dress"


def test_swap_proposes_another_product_for_the_same_need():
    first = agent().run(None, DEMO)
    shoes = next(i for i in first.proposal["items"] if i["need"] == "white sneakers")
    swap = f"بدّل white sneakers: ماشي «{shoes['title']}» (id {shoes['id']})، اقترح لي منتج آخر لنفس الحاجة في نفس الميزانية."
    second = agent().run(first.messages, swap, products=first.products)
    assert second.status == "proposal"
    again = next(i for i in second.proposal["items"] if i["need"] == "white sneakers")
    assert again["id"] != shoes["id"] and second.proposal["within_budget"]
    assert {i["need"] for i in second.proposal["items"]} == {"white sneakers", "summer dress"}   # the dress stays
    plan_calls = [json.loads(c["function"]["arguments"]) for m in second.messages for c in m.get("tool_calls") or []
                  if c["function"]["name"] == "plan_basket"]
    assert plan_calls[-1]["exclude_ids"] == [shoes["id"]]                 # the swap turn's plan excludes the rejected product


def test_photo_without_words_asks_what_to_find():
    result = agent().run(None, "", image_data_url="data:image/png;base64,iVBORw0KGgo=")
    assert result.status == "question" and "الصورة" in result.question["question_darija"]
    assert result.messages[1]["content"][1]["type"] == "image_url"       # the photo reaches the model


class Scripted:
    """A fake model that returns a fixed list of turns (to test the loop's guards)."""
    name = "scripted"

    def __init__(self, turns):
        self.turns = list(turns)

    def complete(self, messages, tools):
        return self.turns.pop(0)


def test_bad_tool_arguments_are_reported_to_the_model_not_raised():
    model = Scripted([ModelTurn(tool_calls=[ToolCall("1", "search_catalogue", {"need": "x"})]),
                      ModelTurn(tool_calls=[ToolCall("2", "nonexistent", {})]),
                      ModelTurn(content="واش من لون؟")])
    result = ShoppingAgent(model, DemoCatalogue()).run(None, "x")
    assert [s.ok for s in result.steps] == [False, False, True]
    assert result.status == "question" and result.question["question_darija"] == "واش من لون؟"
    tool_messages = [m for m in result.messages if m["role"] == "tool"]
    assert "invalid arguments" in tool_messages[0]["content"] and "unknown tool" in tool_messages[1]["content"]


def test_propose_without_plan_is_refused_and_step_budget_is_enforced():
    loop = [ModelTurn(tool_calls=[ToolCall(str(i), "propose_basket", {"message_darija": "x", "message_en": "x"})]) for i in range(20)]
    result = ShoppingAgent(Scripted(loop), DemoCatalogue(), max_steps=3).run(None, "x")
    assert result.status == "error" and len(result.steps) == 3 and not any(s.ok for s in result.steps)


def test_meta_model_request_shape_and_tool_call_parsing():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "search_catalogue", "arguments": "{\"need\": \"dress\", \"query\": \"robe\"}"}}]}}]})
    model = MetaChatModel(api_key="test-key", client=httpx.Client(transport=httpx.MockTransport(handler)))
    turn = model.complete([{"role": "developer", "content": "x"}, {"role": "user", "content": "روبة"}], [{"type": "function"}])
    assert turn.tool_calls[0].name == "search_catalogue" and turn.tool_calls[0].arguments == {"need": "dress", "query": "robe"}
    body = seen["body"]
    assert body["model"] == "muse-spark-1.3" and body["reasoning_effort"] == "low" and body["tool_choice"] == "auto"
    assert "temperature" not in body and "max_tokens" not in body and body["max_completion_tokens"] >= 2000
    assert seen["auth"] == "Bearer test-key"


def test_meta_model_errors():
    with pytest.raises(ModelError):
        MetaChatModel(api_key="").complete([], [])
    cut = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": ""}}]})))
    with pytest.raises(ModelError, match="cut off"):
        MetaChatModel(api_key="k", client=cut).complete([], [])
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, text="slow down")))
    with pytest.raises(ModelError, match="429"):
        MetaChatModel(api_key="k", client=bad).complete([], [])


def test_understanding_searches_at_once_so_the_model_can_plan_directly():
    """Three model calls, not four or more: understand (searches run inside), plan, propose."""
    model = Scripted([
        ModelTurn(tool_calls=[ToolCall("1", "record_understanding", {
            "items": [{"need": "white sneakers", "search_keywords": "baskets blanc"}, {"need": "dress", "search_keywords": "robe"}],
            "budget_dzd": 15000, "summary_darija": "صباط وروبة", "summary_en": "sneakers and a dress"})]),
        ModelTurn(tool_calls=[ToolCall("2", "plan_basket", {"budget_dzd": 15000, "needs": [
            {"need": "white sneakers", "candidate_ids": ["demo-snk-white-1"]}, {"need": "dress", "candidate_ids": ["demo-dress-1"]}]})]),
        ModelTurn(tool_calls=[ToolCall("3", "propose_basket", {"message_darija": "هاك", "message_en": "here"})]),
    ])
    result = ShoppingAgent(model, DemoCatalogue()).run(None, "x")
    assert [s.tool for s in result.steps] == ["record_understanding", "search_catalogue", "search_catalogue", "plan_basket", "propose_basket"]
    searches = json.loads(result.messages[3]["content"])["searches"]          # the tool result of record_understanding
    assert [s["need"] for s in searches] == ["white sneakers", "dress"] and all(s["products"] for s in searches)
    assert result.status == "proposal" and len(result.proposal["items"]) == 2


def _png_data_url(width=40, height=30):
    import base64
    import io
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(out, format="PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


def test_photo_items_are_located_with_the_segmenter_and_cut_out():
    from agent.segment import MockSegmenter, parse_boxes
    boxes = parse_boxes("<0f>0<|box;x1=251;y1=70;x2=923;y2=853;w=1280;h=854|><|mask;x=0;y=0;data=784,673,abc|>,1<|box;x1=5;y1=6;x2=7;y2=8;w=1280;h=854|>")
    assert [(b.x1, b.y1, b.x2, b.y2) for b in boxes] == [(251, 70, 923, 853), (5, 6, 7, 8)] and boxes[0].width == 1280
    result = ShoppingAgent(MockChatModel(), DemoCatalogue(), segmenter=MockSegmenter()).run(None, "صباط أبيض مقاس 40", image_data_url=_png_data_url())
    assert result.status == "proposal"
    located = [s for s in result.steps if s.tool == "locate_in_photo"]
    assert len(located) == 1 and located[0].detail["count"] == 1 and located[0].detail["thumbnails"][0].startswith("data:image/jpeg;base64,")
    assert [s.tool for s in result.steps][:3] == ["record_understanding", "locate_in_photo", "search_catalogue"]
    tool_result = json.loads(result.messages[3]["content"])
    assert tool_result["photo"] == {"white sneakers": {"matches": 1}}
    # without a photo, no segmentation step and no "photo" key
    plain = ShoppingAgent(MockChatModel(), DemoCatalogue(), segmenter=MockSegmenter()).run(None, "صباط أبيض مقاس 40")
    assert not [s for s in plain.steps if s.tool == "locate_in_photo"] and "photo" not in json.loads(plain.messages[3]["content"])


def test_meta_client_retries_model_not_found_then_falls_back(monkeypatch):
    import agent.llm as llm_mod
    monkeypatch.setattr(llm_mod, "RETRY_DELAYS", (0, 0))
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body["model"])
        if body["model"] == "muse-spark-1.3":
            return httpx.Response(404, json={"error": {"code": "model_not_found", "message": "The requested model was not found."}})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "OK", "tool_calls": []}}]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    turn = MetaChatModel(api_key="k", client=client).complete([{"role": "user", "content": "hi"}], [])
    assert turn.content == "OK"
    assert calls == ["muse-spark-1.3", "muse-spark-1.3", "muse-spark-1.3", "muse-spark-1.2"]   # 1 try + 2 retries, then the fallback
