#!/usr/bin/env sh
# One command to run the agent locally (macOS / Linux). First run creates the virtualenv and .env.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env (offline demo mode). To use Meta's models, set WFAGENT_LLM=meta, WFAGENT_STT=meta,"
  echo "WFAGENT_SEGMENT=meta, WFAGENT_CATALOGUE=wfarhali and your MODEL_API_KEY in .env, then run again."
fi
echo "Open http://localhost:8000"
exec uvicorn web.app:app --port 8000
