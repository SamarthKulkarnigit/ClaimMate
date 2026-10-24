# ClaimMate frontend

React + TypeScript + Vite + React Flow. From repo root:

```sh
npm ci --prefix frontend
npm run dev --prefix frontend
```

Open `http://127.0.0.1:5173`. **Synthetic preview** runs without a backend or API key. Choose one of three claims and Run demo; clean/partial claims pause for review, while the mismatch shows two Auditor send-backs then escalates. Approved previews expose clearly synthetic PDF/email samples. Nothing is submitted to an insurer.

```sh
npm test --prefix frontend
npm run build --prefix frontend
```

## Live backend

Choose **Live backend** in the header. If `/api/health` reports `mock: true` (`LLM_MOCK=1`), the UI shows a banner and a `LIVE · MOCK LLM` badge: agent answers are canned, though tools, rules and audit code run for real. Vite proxies `/api` to `http://127.0.0.1:8000`. Set shell variable `CLAIMMATE_API_TARGET` to change the dev proxy target. Optional `VITE_API_BASE` changes the client prefix; cross-origin deployments require appropriate backend CORS. Never put Ollama credentials in a `VITE_*` variable. A production host must proxy `/api` itself.

Uses `docs/PLAN.md` unchanged:

- `POST /api/claims`: multipart `photos[]`, `story`, `accident_date`, JSON strings `vehicle`, `policy`.
- `GET /api/demo`; `POST /api/demo/{name}`.
- `GET /api/claims/{id}` for canonical state. SSE carries activity; state is refreshed on stage completion.
- `GET /api/claims/{id}/events`: supports both default `data:` messages and named `event:` frames using the plan’s JSON envelope. Keepalive comments are ignored by EventSource. Reconnect uses browser SSE reconnect behaviour; replayed identical events are deduplicated. Persist event IDs server-side for reliable replay across browser refreshes.
- Only a run-level `error` event (`data.status === "error"`) ends the assessment. Agent-level errors, such as a vision failure on one photo, mark that node failed and keep listening.
- `POST /api/claims/{id}/approve`: `{approved, note}`. UI approval requires a passed audit and an explicit interrupt. The backend must enforce that check too.
- `GET /api/claims/{id}/pdf`; email text comes from `outputs.email_text`.

`photos[].path` is a server filesystem path, so it is never turned into an image URL. New uploads keep browser object-URL previews. Backend claims use `photos[].url` (`/api/claims/{id}/photos/{P1}`), which Role A's API now provides.

UI masks registration/policy identifiers, renders model text as text, and only accepts HTTP(S) source links. Photos remain original evidence and may themselves contain identifiers. No submission/download approval is performed automatically.

The source-policy PDF is currently unavailable locally (official server returns 403). The Data & sources page says so. Integration with Role A's FastAPI backend is verified in mock-LLM mode. Real-model runs need an Ollama key, and RAG over the actual policy needs that PDF.

Validation: production build; nine event/API/validation tests; live-mode browser E2E against the FastAPI backend (`LLM_MOCK=1`) for all ten demo claims, approve/reject, PDF and email; preview browser checks of clean approval/email, two-retry escalation/approval blocking, partial coverage, rejection withholding outputs, and a 390px mobile layout without page overflow. See `backend/tools/README.md` for tool validation and integration details.
