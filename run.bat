@echo off
REM One command to run the agent locally (Windows). First run creates the virtualenv and .env.
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate
pip install -q -r requirements.txt
if not exist .env (
  copy .env.example .env >nul
  echo Created .env in offline demo mode. To use Meta's models, set WFAGENT_LLM=meta, WFAGENT_STT=meta,
  echo WFAGENT_SEGMENT=meta, WFAGENT_CATALOGUE=wfarhali and your MODEL_API_KEY in .env, then run again.
)
echo Open http://localhost:8000
uvicorn web.app:app --port 8000
