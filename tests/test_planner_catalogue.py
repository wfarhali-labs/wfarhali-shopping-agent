import httpx

from agent.catalogue import DemoCatalogue, WfarhaliCatalogue
from agent.planner import plan_basket


def test_plan_fits_budget_and_prefers_relevance():
    needs = {"sneakers": [("a", 6900), ("b", 5400)], "dress": [("c", 7400), ("d", 4900)]}
    plan = plan_basket(needs, 15000)
    assert plan.within_budget and plan.total_dzd == 14300
    assert [c.product_id for c in plan.choices] == ["a", "c"]          # both first choices fit


def test_plan_trades_down_when_needed_and_reports_overrun():
    needs = {"sneakers": [("a", 6900), ("b", 5400)], "dress": [("c", 7400), ("d", 4900)]}
    plan = plan_basket(needs, 12000)
    assert plan.within_budget and plan.total_dzd <= 12000
    tight = plan_basket(needs, 9000)
    assert not tight.within_budget and tight.total_dzd == 10300 and tight.over_by == 1300   # cheapest, with the gap


def test_plan_without_budget_and_missing_prices():
    plan = plan_basket({"watch": [("w", 4500)], "bag": [("x", None)]})
    assert plan.within_budget and plan.total_dzd == 4500 and plan.missing == ("bag",)


def test_demo_catalogue_keyword_search():
    found = DemoCatalogue().search("baskets blanches")
    assert found and found[0].id.startswith("demo-snk-white")
    assert all(p.price_dzd for p in found)


def test_wfarhali_catalogue_reads_public_fields_only():
    def handler(request):
        assert request.url.path == "/api/live-search" and request.url.params["q"] == "robe femme"
        return httpx.Response(200, json={"status": "ok", "results": [
            {"id": 7, "title": "Robe", "source_store": "temu", "estimate_dzd": 7400, "pricing_category": "fashion",
             "image_url": "https://img/x.jpg", "product_url": "https://store/7", "source_price": "9.90"},
            {"id": 8, "title": "Robe 2", "source_store": "temu", "estimate_dzd": None}]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    found = WfarhaliCatalogue(base_url="https://wfarhali.test", client=client).search("robe femme")
    assert found[0].price_dzd == 7400 and found[0].store == "TEMU" and found[1].price_dzd is None
    assert "source_price" not in found[0].public()                     # the store price is never exposed


def test_wfarhali_catalogue_unavailable_returns_nothing():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503, json={"status": "unavailable"})))
    assert WfarhaliCatalogue(client=client).search("x") == []
