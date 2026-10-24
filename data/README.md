# Data provenance and demo fixtures

All amounts are INR. Catalogue checked on **24 October 2026**. `prices.csv` has 21 rows: 10 Swift, 11 Baleno. Each row has the requested six columns plus `part_number` and `fitment_note` for traceability.

Prices are observed MRP from [Maruti Suzuki Genuine Parts](https://www.marutisuzuki.com/genuine-parts). Category URLs identify the exact SKU in `part_number`. Prices and fitment vary by year/trim and may change. The Baleno rear bumper page shows INR 4,100; its alternate short URL shows INR 4,056. The catalogue uses the descriptive product page and explicitly records that discrepancy. That page omits fitment: application to the Baleno demo is an assumption requiring VIN confirmation. Materials are engineering classifications, not manufacturer-certified composition.

`labour.json` contains **assumptions**, not sourced garage quotes. No fallback rate exists for unknown operations. Painting values represent consolidated bills; the demo replacement estimates exclude painting and say so on each line. Production estimates need the actual garage’s scope and charges.

`depreciation.json` records the fixed schedule from [Royal Sundaram Stand-Alone Motor Own Damage Policy, Rev 2023](https://www.royalsundaram.in/assets/standalone-motor-own-damage-policy-private-car-rev2023.pdf). Deductions use replacement-part age bands, not IDV depreciation. The zero-dep flag is a demo simplification and requires actual add-on verification. Deductible amounts are corroborated by [ICICI Lombard’s motor insurance FAQs](https://www.icicilombard.com/info-center/faqs).

## Ten scenarios

| Fixture | Expected result |
| --- | --- |
| `clean_swift_front` | Bumper + headlamp covered; audit pass; human review |
| `partial_baleno_rear` | Rear bumper + left tail lamp covered; pre-existing mechanical engine fault excluded |
| `mismatch_front_rear` | A4 fails; two send-backs; surveyor escalation |
| `duplicate_photo` | A2 matches the synthetic prior-claim hash; escalate for review |
| `exif_before_policy` | A1: EXIF is before policy start; escalate |
| `plate_mismatch` | A3: fixture plate label differs; one re-check then escalate |
| `blurry_photo` | A6: request clear evidence; surveyor escalation |
| `zero_dep` | Depreciation 0% with assumed applicable add-on |
| `six_year_old` | Metal replacement depreciation 40% |
| `windshield_only` | Glass depreciation 0% |

All images are **synthetic technical diagrams**, not vehicle photographs. EXIF and hashes exercise actual tools. Plate reads, damage classifications, confidence, coverage and story consistency are scripted expectations. The diagrams do not validate vision accuracy. In particular, the engine exclusion assumes an inspection found pre-existing mechanical failure; noise alone does not establish an exclusion.

The input `claim.json` stays separate from `expected_state.json`. The answer key is a dictionary keyed by directory name. The three frontend replays are generated from these fixtures using Python tool calculations. Never use expected-state files as LLM evaluation inputs or report their agreement as measured accuracy.

Regenerate from the repository root with `.venv/bin/python -m data.generate_fixtures`. Replace diagrams with authorized real photos before model evaluation; update input EXIF/hashes, expected labels and the prior-claim index together. Resolve photo paths relative to repo root.

## Policy clauses (`policy/clauses.json`)

Added by Role A for BM25 retrieval. `text` is intended policy wording (some entries abridged). `note` holds plain-English explanations that must not be quoted as wording. Every clause is marked `verified_against_pdf: false` until checked against the official PDF. `ADDON.ZERO_DEP` paraphrases a typical add-on, not standard wording.

`past_claims_hashes.json` stays a committed one-record synthetic fixture. Completed live claims are indexed at runtime in the gitignored `outputs/claim_hashes.json`.

## Remaining materials

- Official policy PDF: server download is blocked (HTTP 403); see `policy/README.md`.
- Real demo photos and presentation deck: Samarth will provide later. Slide edits and measured model-results figures are pending those files and Role A integration.
