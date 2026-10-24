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

## Integration still required from Role A

1. Import these implementations in intake, cost and finalize; preserve error states rather than treating missing data as zero/clean.
2. Serve the API and SSE routes specified in `docs/PLAN.md`, with durable claim state retrievable by GET.
3. On human interrupt, leave the claim in `next='human'`; emit `interrupt`. On resume emit fresh events and a final `done` after `outputs.pdf_path` and `outputs.email_text` are persisted. Enforce approval and retry limits on the server.
4. Local `photos[].path` is not a browser URL. Uploaded photos use local browser previews; backend demos need an optional `photos[].url` under `/api/` or a new agreed evidence-serving route. This optional UI extension is documented, not assumed to exist.
5. Supply the policy PDF at `data/policy/standard_od_policy.pdf` before RAG ingestion. Official download attempts returned HTTP 403. No substitute or generated policy was inserted.
6. Run the ten claims through the real agents after real damage photos are supplied. Record model agreement separately from unit-test results.

Validation: 64 Python tests cover depreciation boundaries, paint material, invalid inputs, EXIF, pHash thresholds, date checks, catalogue provenance, fixture isolation, PDF text/masking and pagination. The sample PDF was rendered and visually checked. Full backend/LLM integration remains pending.
