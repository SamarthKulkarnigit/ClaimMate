# ClaimMate

A team of AI agents that turns accident photos and your policy into a fully explained, ready-to-file motor insurance claim.
AgentOps 2026 · Team Dent Detectives · Track 01 Multi-agent systems. Architecture & plan: [docs/PLAN.md](docs/PLAN.md)

## Run the backend (Windows PowerShell, from repo root)

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass; .\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
copy .env.example .env      # then put your OLLAMA_API_KEY in .env

# 1) offline smoke test of the whole agent graph (no API calls)
$env:LLM_MOCK="1"; python -m scripts.eval
# 2) real models
$env:LLM_MOCK="0"; python -m scripts.eval clean_swift_front
# 3) API server for the UI
uvicorn backend.app.main:app --reload --port 8000
```

## Run the full app (2 terminals)

```powershell
# terminal 1 - backend (LLM_MOCK=1 = canned answers, no API calls; 0 = real Ollama models)
$env:LLM_MOCK="1"; uvicorn backend.app.main:app --reload --port 8000
# terminal 2 - frontend (Vite proxies /api -> :8000)
cd frontend; npm install; npm run dev     # open http://127.0.0.1:5173
```

Evaluate all 10 demo claims against `data/answer_key.json`: `python -m scripts.eval`

## API (for the frontend)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | models + mock flag |
| GET | `/api/demo` | list demo claims |
| POST | `/api/demo/{name}` | start a demo claim → `{claim_id}` |
| POST | `/api/claims` | multipart: `photos[]`, `story`, `accident_date`, `vehicle` (JSON str), `policy` (JSON str) |
| GET | `/api/claims/{id}/events` | **SSE** stream of agent events (see PLAN §4.2) |
| GET | `/api/claims/{id}` | `{status, state}` — full claim state, photo URLs |
| POST | `/api/claims/{id}/approve` | `{approved: true/false, note}` — resumes the graph |
| GET | `/api/claims/{id}/pdf` | claim file |
| GET | `/api/claims/{id}/photos/{P1}` | evidence photo |

Status values: `running` → `awaiting_approval` → `filed` / `rejected`, or `escalated`, or `error`.

## Layout

- `backend/agents/` — LangGraph graph + agent nodes (Coordinator, Damage Assessor, Policy Analyst, Cost Estimator, Auditor, Human, Finalize, Escalate)
- `backend/tools/rules.py` — depreciation, deductible, price lookup (fixed rules, **no LLM**)
- `backend/tools/forensics.py` — EXIF date + perceptual-hash duplicate check
- `backend/tools/claim_file.py` — claim PDF + insurer email
- `backend/rag/search.py` — BM25 over policy clauses (`data/policy/clauses.json` + PDF if present)
- `data/demo_claims/*/claim.json` — demo + test claims with `expected` answer key and offline `mock` answers
- `scripts/eval.py` — runs all claims, prints agreement % (Results slide)
