# Policy source required for RAG

Expected destination: `data/policy/standard_od_policy.pdf`.

Official source, Royal Sundaram Stand-Alone Motor Own Damage Policy - Private Car, Rev 2023:

- https://my.royalsundaram.in/sites/default/files/2023-10/Standalone_Motor_Own_Damage_Policy_Private_Car_Rev2023.pdf
- https://www.royalsundaram.in/assets/standalone-motor-own-damage-policy-private-car-rev2023.pdf

Both returned HTTP 403 on 24 October 2026. An alternate insurer forms-library URL was also blocked. No fabricated PDF or different policy is supplied. Place a legitimately obtained copy here, verify its title/revision, then run Role A’s ingestion.

The indexed official wording corroborates the fixed rules in `../depreciation.json`. The only verbatim policy excerpt in demo replays is the short Section I(vi) phrase `by accidental external means;`. The mechanical exclusion is paraphrased and clearly labelled as a scenario assumption; validate its locator against the actual PDF before real RAG use.
