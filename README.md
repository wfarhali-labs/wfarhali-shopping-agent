# Wfarhali Shopping Agent

**An AI shopping agent for Algeria.** A customer types, speaks or sends a photo, in **Algerian Arabic (Darija)**, Arabic or French. The agent understands the request, searches partner stores, plans a basket **within the customer's budget in Algerian dinars (DZD)**, asks when something is unclear, and prepares a price request that the customer confirms.

> Darija is the Algerian Arabic dialect spoken by about 45 million people. Most AI tools do not understand it, yet it is how Algerians actually talk, and send voice notes, when they shop.

Built for the **Meta Global AI Developer Hackathon** (Oct 26 – Nov 4, 2026), track *Startups*, problem statement *Build for Your World*.

## What existed before the hackathon, and what was built during it

| Before the hackathon (not part of this repository) | Built during the hackathon (this repository) |
|---|---|
| **Wfarhali** ([wfarhali.com](https://wfarhali.com)), a live service: customers in Algeria order products from international stores, Wfarhali verifies, prices in DZD, pays and delivers. | The **agent**: a tool-calling loop driven by Meta's Muse Spark (`agent/agent.py`, `agent/tools.py`). |
| Its product search endpoint `/api/live-search`, which returns, for each product, an **estimated total in DZD** computed by Wfarhali's own pricing system (closed source). | The **budget planner** (`agent/planner.py`): exact arithmetic to fit one product per need into the budget. |
| | The **multimodal input**: voice recorded and converted to WAV in the browser for Muse Voice Transcribe, photos sent to Muse Spark (`agent/speech.py`, `web/`). |
| | The **web app** (`web/`): every agent step shown to the customer, in Darija with an English line. |
| | An **offline mock model** (`agent/mock_llm.py`, `agent/darija.py`) and a synthetic demo catalogue, so everything runs and is tested without any API key. |

The agent only *calls* Wfarhali's public search endpoint as a tool; no Wfarhali code, data or pricing logic is in this repository. Commit history shows the build dates.

## How it works

```
customer: text / voice / photo (Darija, Arabic, French)
        │
        ▼
Muse Voice Transcribe ─► Muse Spark (tool calling, sees photos)
                              │ 1. record_understanding  products, sizes, colours, budget, wilaya;
                              │                          the agent searches the catalogue for each item at once
                              │    (search_catalogue      only to retry a need with other French keywords)
                              │ 2. plan_basket           exact budget arithmetic (planner.py)
                              │ 3. propose_basket  or  ask_customer
                              ▼
        web app: transparent steps ─► proposal ─► customer confirms
```

Design choices:
- **The model decides, tools compute.** Muse Spark chooses what to search and which products are relevant; prices come only from tool results and totals from the planner, so the agent never invents a number.
- **Honest over budget.** When nothing fits, the agent shows the cheapest basket and by how much it is over.
- **One clarifying question** when the request is not actionable, then it continues with the whole conversation.
- **Few model calls.** The catalogue searches run inside the understanding step, so a request needs three model calls (understand, plan, propose) whatever the number of products; the conversation is prompt-cached.
- **Human in the loop.** Nothing is ordered without the customer's confirmation; Wfarhali's team confirms the final price.

## Meta models

| Model | Use | Status |
|---|---|---|
| **Muse Spark** (`muse-spark-1.3`, Meta Model API, Chat Completions + tools) | understanding, decisions, tool calls, reading photos | **live loop verified (Oct 27)**: a Darija request ran through the full loop (understand → search → plan → propose) in 4 model calls, about 9,000 tokens in total with prompt caching; photos not yet run live |
| **Muse Voice Transcribe** (`muse-voice-transcribe-1.0`) | Darija / French voice notes to text | client written and unit-tested against the documented API shape; live run not yet done |
| SAM 3.1 | product cut-out from photos | planned |

## Run it

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                               # offline by default: mock model + demo catalogue
uvicorn web.app:app --port 8000                    # open http://localhost:8000
pytest -q
```

To use Meta's models and the live Wfarhali catalogue, set in `.env`:
```
WFAGENT_LLM=meta
WFAGENT_STT=meta
MODEL_API_KEY=...            # Meta Model API key (never commit it)
WFAGENT_CATALOGUE=wfarhali
```

## Repository map

```
agent/agent.py       the agent loop (model ⇄ tools), step trace
agent/tools.py       tool schemas + system prompt
agent/llm.py         Muse Spark client (Meta Model API) and the model interface
agent/mock_llm.py    offline stand-in model; agent/darija.py its small Darija reader
agent/planner.py     budget planner
agent/catalogue.py   Wfarhali search API client + offline demo catalogue
agent/speech.py      Muse Voice Transcribe client + offline mock
web/                 FastAPI app and the single-page UI
tests/               pytest suite
```

## License

MIT. The demo catalogue (`data/demo_catalogue.json`) is synthetic.
