import json

import httpx
import pytest

from agent import darija
from agent.agent import ShoppingAgent
from agent.catalogue import DemoCatalogue
from agent.llm import MetaChatModel, ModelError, ModelTurn, ToolCall
from agent.mock_llm import MockChatModel

DEMO = "حاب صباط أبيض مقاس 40 وروبة صيف، الميزانية 15 ألف، والتوصيل لباتنة"


def agent():
    return ShoppingAgent(MockChatModel(), DemoCatalogue())


def test_darija_reader_understands_the_demo_sentence():
    request = darija.parse(DEMO)
    assert [i.need for i in request.items] == ["white sneakers", "summer dress"]
    assert request.items[0].size == "40" and request.items[0].search_keywords == "baskets blanc"
    assert request.budget_dzd == 15000 and request.wilaya == "Batna"
    assert darija.parse("ساعة لمرا بـ ٥ آلاف").budget_dzd == 5000          # Arabic-Indic digits
    assert darija.parse("baskets blanches et robe, 12000 da").budget_dzd == 12000


def test_full_turn_proposes_a_basket_within_budget():
    result = agent().run(None, DEMO)
    assert result.status == "proposal"
    assert [s.tool for s in result.steps] == ["record_understanding", "search_catalogue", "search_catalogue", "plan_basket", "propose_basket"]
    proposal = result.proposal
    assert proposal["within_budget"] and proposal["total_dzd"] <= 15000
    assert {i["need"] for i in proposal["items"]} == {"white sneakers", "summer dress"}
    assert result.understanding["summary_en"].startswith("white sneakers size 40 + summer dress")
    assert "التوصيل" in result.understanding["summary_darija"]


def test_over_budget_is_said_honestly():
    result = agent().run(None, "صباط أسود وساعة رجالي بـ 8 آلاف")
    assert result.status == "proposal" and not result.proposal["within_budget"]
    assert result.proposal["over_by_dzd"] == result.proposal["total_dzd"] - 8000 > 0


def test_unclear_request_gets_one_question_then_continues():
    first = agent().run(None, "سلام، عندي عرس الجمعة")
    assert first.status == "question" and first.question["question_en"]
    second = agent().run(first.messages, "روبة سهرة بـ 12 ألف")
    assert second.status == "proposal" and second.proposal["items"][0]["need"] == "dress"


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
