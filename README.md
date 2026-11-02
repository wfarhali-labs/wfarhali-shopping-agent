# Wfarhali Shopping Agent

**An AI shopping agent for Algeria.** A customer types, speaks or sends a photo, in **Algerian Arabic (Darija)**, Arabic, French or English. The agent understands the request, searches Wfarhali's live catalogue of international stores, plans a basket **within the customer's budget in Algerian dinars (DZD)**, asks when something is unclear, and hands the confirmed basket to Wfarhali's team.

Built on **Muse Spark 1.3**, **Muse Voice Transcribe** and **SAM 3.1** (Meta Model API). Team: Wfarhali (EURL, Algeria), Startup track.

> Darija is the Algerian Arabic dialect spoken by about 45 million people. Most mainstream AI tools handle it poorly, and almost none lets you shop in it, yet it is how Algerians actually talk, and send voice notes, when they buy.

Built for the **Meta Global AI Developer Hackathon** (Oct 26 – Nov 4, 2026), problem statement *Build for Your World*. Pitch: [`docs/PITCH.md`](docs/PITCH.md). Demo video script: [`docs/VIDEO_SCRIPT.md`](docs/VIDEO_SCRIPT.md).

## What existed before the hackathon, and what was built during it

| Before the hackathon (not part of this repository) | Built during the hackathon (this repository) |
|---|---|
| **Wfarhali** ([wfarhali.com](https://wfarhali.com)), a live service: customers in Algeria order products from international stores, Wfarhali verifies, prices in DZD, pays and delivers. | The **agent**: a tool-calling loop driven by Meta's Muse Spark (`agent/agent.py`, `agent/tools.py`). |
| Its product search endpoint `/api/live-search`, which returns, for each product, an **estimated total in DZD** computed by Wfarhali's own pricing system (closed source). | The **budget planner** (`agent/planner.py`): exact arithmetic to fit one product per need into the budget. |
| | The **multimodal input**: voice recorded and converted to WAV in the browser for Muse Voice Transcribe, photos sent to Muse Spark, the item located in the photo with SAM 3.1 (`agent/speech.py`, `agent/segment.py`, `web/`). |
| | The **web app** (`web/`): a chat page in Darija or English (EN switch), with swap and confirm buttons; the agent's work log is available with `?debug=1`. |
| | An **offline mock model** (`agent/mock_llm.py`, `agent/darija.py`) and a synthetic demo catalogue, so everything runs and is tested without any API key. |

The agent only *calls* Wfarhali's public search endpoint as a tool; no Wfarhali code, data or pricing logic is in this repository. Commit history shows the build dates.

## How it works

```
customer: text / voice / photo (Darija, Arabic, French, English)
        │
        ▼
Muse Voice Transcribe ─► Muse Spark (tool calling, sees photos)
                              │ 1. record_understanding  products, sizes, colours, budget;
                              │                          with a photo: SAM 3.1 locates each item (check + cut-out);
                              │                          the agent searches the catalogue for each item at once
                              │    (search_catalogue      only to retry a need with other French keywords)
                              │ 2. plan_basket           exact budget arithmetic (planner.py)
                              │ 3. propose_basket  or  ask_customer
                              ▼
        web app: answer (or one question) ─► swap ─► confirm ─► WhatsApp to Wfarhali's team
```

Design choices:
- **The model decides, tools compute.** Muse Spark chooses what to search and which products are relevant; prices come only from tool results and totals from the planner, so the agent never invents a number.
- **Money the way Algerians say it.** Budgets are often given in centimes ("300 alf" = 3,000 DZD, "melyoun w nos" = 15,000 DZD); the agent converts, repeats the amount in DZD in its summary so the customer can correct it, and asks when the reading is unclear.
- **Honest over budget.** When nothing fits, the agent does not hide products or bend prices: it proposes the closest basket and says plainly by how much it is over ("a nice dress, but 150 DZD over your 5,000 budget"), and the customer decides.
- **Swap.** Each proposed product has a "بدّل · Swap" button: the agent re-plans the basket without the rejected product (two model calls, no new search) and keeps the other choices.
- **One clarifying question** when the request is not actionable, with 2 to 4 tappable answers when the answer is a choice, then it continues with the whole conversation.
- **Few model calls.** The catalogue searches run inside the understanding step, so a request needs three model calls (understand, plan, propose) whatever the number of products; the conversation is prompt-cached.
- **Human in the loop.** Nothing is ordered without the customer's confirmation: "Confirm" opens WhatsApp with the basket written out (products, links, total, budget, sizes and colours) for the customer to send to Wfarhali's team, who confirm the final price. The agent never writes to Wfarhali's systems.

## Meta models

| Model | Use | Status |
|---|---|---|
| **Muse Spark** (`muse-spark-1.3`, Meta Model API, Chat Completions + tools) | understanding, decisions, tool calls, reading photos | **live verified (Oct 27–Nov 2)**: Darija, French and English requests run through the full loop (understand + search → plan → propose) in 3 model calls against the live Wfarhali catalogue, with centime budgets, clarifying questions, the swap flow and photos |
| **Muse Voice Transcribe** (`muse-voice-transcribe-1.0`) | Darija / French voice notes to text | verified live (Nov 2) with a real Darija voice note recorded on a phone and sent as a file: transcript correct, basket proposed |
| **SAM 3.1** (`sam-3.1`, Responses API) | locating the item in the customer's photo: Muse Spark names what it sees, SAM 3.1 is asked for that noun phrase; 0 matches = re-read or ask, 2+ = ask which one, 1 = the cut-out is shown to the customer | verified live (Nov 2) with a real product photo: item located, catalogue searched, honest proposal above the stated budget |

## For judges: run it in 3 minutes

```bash
git clone https://github.com/wfarhali-labs/wfarhali-shopping-agent.git
cd wfarhali-shopping-agent
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```
Open `.env` and set `WFAGENT_LLM=meta`, `WFAGENT_STT=meta`, `WFAGENT_SEGMENT=meta`, `WFAGENT_CATALOGUE=wfarhali` and your own Meta Model API key in `MODEL_API_KEY` (no key is in this repository). Then:
```bash
uvicorn web.app:app --port 8000        # open http://localhost:8000
```
The customer only sees the answer; add `?debug=1` to the URL to keep the agent's work log on screen (understanding, searches, planning, photo check). The **EN** button at the top right switches the page to English (English first, the agent's Darija under it, English examples); the agent also understands English requests. Things to try (Darija, Arabic, French or English):
- `نحوس على بوت شتاء أسود مقاس 39 وفاست، الميزانية 2 ملاين` → black winter boots and a jacket from Wfarhali's catalogue within 20,000 DZD ("2 mlayen" is 2 million centimes).
- `نحوس على روبا تاع خرجة بـ 300 ألف` → budget read as 3,000 DZD; nothing fits, so the cheapest dress is proposed with the overrun stated.
- `صباط بـ 15 ألف` → the amount is ambiguous (150 DZD?), the agent asks which one you meant.
- `عندي عرس الجمعة` → one clarifying question, then answer `روبة سهرة بـ مليون و200`.
- Press **بدّل · Swap** on a product → another product for the same need, the rest of the basket unchanged.
- Send a photo of a product with a word or two → SAM 3.1 locates the item and the cut-out is shown; 0 or several matches make the agent ask.
- Press the microphone and speak in Darija, or send a voice-note file (WhatsApp, phone recorder) with the note button → Muse Voice Transcribe (the microphone needs HTTPS or localhost).
- Press **أكّد · Confirm** → WhatsApp opens with the basket written out for Wfarhali's team.

Without a key, `cp .env.example .env` as is runs everything offline on the mock model and the demo catalogue, and `pytest -q` runs the 27 tests.

**Hosting note.** Meta Model API applies a [geographic use policy](https://dev.meta.ai/legal/geographic-use-policy) to the server's outbound IP: from some cloud hosts (observed on Render) the API answers `404 model_not_found` and an empty model list while the same key works from a laptop. Run locally, or check `/api/selftest?n=5` on a host before relying on it.

## Configuration

All settings live in `.env` (see `.env.example`): `WFAGENT_LLM` (`mock` | `meta`), `WFAGENT_STT` (`mock` | `meta`), `WFAGENT_SEGMENT` (`mock` | `meta`), `WFAGENT_CATALOGUE` (`demo` | `wfarhali`), `MODEL_API_KEY` (never committed), `WFAGENT_WHATSAPP` (the number that receives confirmed baskets), and the public-deployment caps `WFAGENT_MAX_TURNS_PER_HOUR_PER_IP` / `WFAGENT_MAX_TURNS_PER_DAY`. `/api/health` shows the active configuration (never the key); `/api/selftest` makes one tiny model call to diagnose a deployment.

## Deploy (optional)

`render.yaml` describes the service: `pip install -r requirements.txt`, then `uvicorn web.app:app --host 0.0.0.0 --port $PORT`, health check on `/api/health`. In the Render dashboard, create a **Blueprint** from this repository and enter `MODEL_API_KEY` as a secret; the other settings (`WFAGENT_LLM=meta`, `WFAGENT_STT=meta`, `WFAGENT_SEGMENT=meta`, `WFAGENT_CATALOGUE=wfarhali`) are in the file. The free plan sleeps after inactivity and takes about a minute to wake up.

Because every turn costs API money, a public deployment is capped: `WFAGENT_MAX_TURNS_PER_HOUR_PER_IP` (default 30) and `WFAGENT_MAX_TURNS_PER_DAY` (default 400, roughly 4 USD a day at the measured cost). Over the cap, the app answers 429 and the page says to try later.

Other hosts: `Procfile` (Railway, Heroku-style) and `Dockerfile` (Koyeb, Fly.io, Cloud Run, Hugging Face Spaces) run the same app; set the same environment variables there. Note: Meta Model API offers models according to where the request comes from. From Render's Oregon region, `muse-spark-1.3` was `model_not_found` while the same key worked elsewhere; the same service in Render's Virginia region works (verified Oct 30). `/api/selftest` shows the models visible from the server.

## Repository map

```
agent/agent.py       the agent loop (model ⇄ tools), parallel searches, photo check, step trace
agent/tools.py       tool schemas + system prompt (Darija, centimes, swap, photo rules)
agent/llm.py         Muse Spark client (Meta Model API): retries, fallback model
agent/speech.py      Muse Voice Transcribe client (+ silence guard) and offline mock
agent/segment.py     SAM 3.1 client (boxes from the special-token output), cut-outs, offline mock
agent/catalogue.py   Wfarhali live search client + offline demo catalogue
agent/ranking.py     re-ranks catalogue results by requested colour and query words
agent/planner.py     budget planner (exact arithmetic, one product per need)
agent/mock_llm.py    offline stand-in model; agent/darija.py its small Darija reader
agent/config.py      settings from the environment
web/app.py           FastAPI app: /api/turn, /api/health, /api/selftest, spending caps
web/static/          single-page UI (Darija / English), logo
data/                synthetic demo catalogue
docs/                pitch and demo video script
tests/               pytest suite (27 tests, offline)
render.yaml, Procfile, Dockerfile   deployment
```

## License

MIT. The demo catalogue (`data/demo_catalogue.json`) is synthetic.
