# Role B tools — integration handoff

Branch: `samarth/role-b`. Implements `docs/PLAN.md` §4.4 without changing the REST or ClaimState contracts. Role A directories are untouched.

From repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/tools/requirements.txt
.venv/bin/python -m pytest backend/tools/tests -q
```

Import with `from backend.tools.depreciation import depreciation_pct` when running from the repo root, or `from tools.depreciation import depreciation_pct` when running from `backend/`.

| Tool | Behaviour |
| --- | --- |
| `depreciation_pct(material, vehicle_age_months, zero_dep)` | Returns a **fraction**: `0.5` = 50%. Age is completed months at accident. Exact boundaries are inclusive at 6/12/24/36/48/60/120 months. Unknown materials raise for classification; `other` is an explicit fallback. |
| `compulsory_deductible(cc)` | INR 1,000 through 1,500 cc, otherwise INR 2,000. Add voluntary deductible once per claim. |
| `paint_depreciation(bill, zero_dep=False, material_itemized=False)` | Added helper: 50% of material only. Material is 25% of a consolidated bill, so effective deduction is 12.5%. If material is itemized, pass its amount and `material_itemized=True`. |
| `part_price(model, part)` | Returns `price`, `source_url`, `checked_on`, plus material, part number and fitment note. Returns `None` when missing. No fuzzy matching or invented fallback prices. |
| `labour_range(part, action)` | Assumed INR bounds for explicitly listed operations. Unsupported operations raise `KeyError`; request a garage quote. |
| `inspect_photo(path)` | Reads nested DateTimeOriginal with DateTime fallback, returns ISO local capture time or None, `has_exif`, and orientation-normalized 64-bit pHash. Invalid/unreadable images raise. `has_exif` does not imply a usable timestamp. |
| `find_duplicate(phash, max_distance=6)` | Nearest prior claim ID within inclusive Hamming threshold, otherwise None. Index is a list of `{claim_id, phash}`. Missing/malformed index raises; it must not be reported as a passed check. |
| `check_photo_date(timestamp, accident_date, start, end)` | Added A1 helper. Returns `ok`, `action`, `detail`. Missing or mismatched timestamps request evidence; out-of-policy dates escalate. EXIF is an untrusted signal, not proof. |
| `build_claim_pdf(state, out_path)` | ReportLab PDF with masked identifiers, table, source URLs, coverage references, exclusions and audit findings. Creates parent folder; returns path. Does not approve or submit. Uses INR text and Latin-1 fallback for unsupported characters. |
| `build_email(state)` | Masked insurer email draft. No sending mechanism. |

## Cost-estimator integration

- `replace`: parts price less part depreciation, plus labour. Account for painting separately if required; demo fixture painting is explicitly excluded.
- `repair`: do not charge a replacement part; use labour plus painting less painting-material depreciation.
- Calculate with decimal arithmetic, round to paise, then subtract compulsory + voluntary deductible once. Clamp the final payable at zero. Respect coverage decisions and actual policy limits.
- `zero_dep=True` assumes the caller verified the add-on applies. It is not proof that every part or every claim qualifies.
- Catalogue rows represent selected variants. `part_price(model, part)` cannot resolve VIN/year/trim; surface `fitment_note` for confirmation. Lamp assemblies are classified as plastic for the demo; verify actual material before real use.
- A pHash match warrants review, not a definitive fraud accusation. Only index completed prior claims; adding the current claim first would create false self-matches.

## Fixtures and outputs

`data/demo_claims/<name>/claim.json` contains input only. `expected_state.json` and `data/answer_key.json` contain expected results and must not be fed to a real vision evaluation. Generate controlled fixtures with:

```sh
.venv/bin/python -m data.generate_fixtures
```

This creates ten diagrams with deterministic EXIF/pHash signals and three scripted UI replays with PDF/email samples. They do not measure model performance. `past_claims_hashes.json` contains exactly one labelled synthetic prior record.

## Integration status (re-verified after Role A's merge, 24 Oct 2026)

The graph uses Role A's `rules.py` (depreciation, prices, labour, estimate lines) and `claim_file.py` (PDF + email) instead of `depreciation.py`, `prices.py`, `claim_pdf.py` and `email_draft.py`. `rules.depreciation_pct` matches `depreciation.depreciation_pct` for every catalogue material at ages 0-159 months, with and without zero-dep. Labour lookups match too. Role B kept `claim_file.py` as the live renderer and patched it:

- Story, LLM reasons, audit details and escalation reasons are escaped and masked. Previously, `<` or `&` in a story crashed finalize.
- The PDF now carries an "estimate for review" line, a synthetic-fixture label, per-line policy text marked unverified, parts-source URLs or "garage quote needed", and the policy source. The evidence-photo heading no longer strands at a page break.
- The email has a synthetic label, estimated payable, and a "DRAFT ONLY - not sent" footer.

`forensics.remember()` records completed live claims in the gitignored `outputs/claim_hashes.json`. `find_duplicate()` reads the committed fixture index plus that runtime index. Live uploads no longer modify `data/past_claims_hashes.json`.

Verified with `LLM_MOCK=1` through the React UI (live mode, Vite proxy):
- the 10 demo claims, with approve and reject;
- PDF and email download;
- SSE replay after resume;
- photo URLs.

Real Ollama inference has not been exercised here (no API key).

### Open items for Role A

1. **Zero-damage loop**: `backend/agents/nodes.py` `coordinator()` tests `not state.get("damages")`. When the Damage Assessor returns `[]` (no parts found, or the vision-failure fallback), it re-routes to `damage` until the recursion limit, and the claim ends in `error` instead of reaching Auditor A6. Fix: `elif state.get("damages") is None:`. Reproduce by uploading any photo with `LLM_MOCK=1`.
2. **Send-back limit**: `MAX_SEND_BACKS` defaults to `1` in `backend/config.py` and `.env.example`. PLAN §3 and the UI ("Re-checks n / 2") expect 2. The mismatch demo currently shows one re-check before escalation.
3. `data/policy/clauses.json`: explanatory glosses were moved from `text` (shown as the policy excerpt) to `note`. Their keywords were copied into `tags`. Demo-story retrieval is unchanged. Part queries keep the same top two clauses; only the weak third match changed (`S1.EXCL.a` → `GE.1`). Consider indexing `note` in `rag/search.py`.
4. Optional: once `MAX_SEND_BACKS` is settled, expose it in `/api/health` so the UI does not hard-code the denominator.

### Still blocked

- Policy PDF at `data/policy/standard_od_policy.pdf`: official downloads return HTTP 403. No substitute was inserted, and `clauses.json` is marked `verified_against_pdf: false`.
- Real damage photos and the presentation deck. Run the ten claims through real agents after real photos arrive, and report model agreement separately from mock-mode and unit-test results.

Validation: `pytest backend` covers depreciation boundaries, paint material, invalid inputs, EXIF, pHash thresholds and the runtime index, date checks, catalogue provenance, fixture isolation, PDF text, masking and pagination, and the live claim file's escaping and labelling.
