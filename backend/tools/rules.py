"""Deterministic money rules. NO LLM in here.

Source: standard Motor Own Damage policy wording (IRDAI / IMT), Section I depreciation
schedule, and IMT.22 compulsory deductible. See data/policy/clauses.json.
"""
from __future__ import annotations

import csv
import json
from datetime import date
from functools import lru_cache

from backend import config

MATERIAL_DEP = {"rubber": 0.50, "nylon": 0.50, "plastic": 0.50, "battery": 0.50, "fibreglass": 0.30, "glass": 0.0}
PAINT_MATERIAL_SHARE = 0.25   # material = 25% of a consolidated paint bill
PAINT_MATERIAL_DEP = 0.50

# (max_age_months_inclusive, rate) for metal & other parts
AGE_DEP = [(6, 0.0), (12, 0.05), (24, 0.10), (36, 0.15), (48, 0.25), (60, 0.35), (120, 0.40)]


def depreciation_pct(material: str, vehicle_age_months: int, zero_dep: bool = False) -> float:
    if zero_dep:
        return 0.0
    m = (material or "metal").lower()
    if m in MATERIAL_DEP:
        return MATERIAL_DEP[m]
    for max_m, rate in AGE_DEP:
        if vehicle_age_months <= max_m:
            return rate
    return 0.50


def depreciation_clause(material: str, zero_dep: bool) -> str:
    if zero_dep:
        return "ADDON.ZERO_DEP"
    return "S1.DEP.MATERIAL" if (material or "metal").lower() in MATERIAL_DEP else "S1.DEP.AGE"


def compulsory_deductible(cc: int) -> int:
    return 1000 if (cc or 0) <= 1500 else 2000


def age_months(reg_date: str, on: str | None = None) -> int:
    r = date.fromisoformat(reg_date)
    d = date.fromisoformat(on) if on else date.today()
    return max(0, (d.year - r.year) * 12 + (d.month - r.month) - (1 if d.day < r.day else 0))


@lru_cache(maxsize=1)
def parts_catalog() -> dict:
    return json.loads((config.DATA / "parts.json").read_text(encoding="utf-8"))["parts"]


@lru_cache(maxsize=1)
def _prices() -> dict:
    out = {}
    with open(config.DATA / "prices.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("price"):
                out[(row["model"].strip().lower(), row["part"].strip())] = {
                    "price": int(float(row["price"])),
                    "source_url": row.get("source_url", ""),
                    "checked_on": row.get("checked_on", ""),
                    "verified": row.get("source_url", "").startswith("http"),
                }
    return out


def part_price(model: str, part: str) -> dict | None:
    return _prices().get(((model or "").lower(), part))


def labour_range(part: str, action: str) -> tuple[int, int]:
    p = parts_catalog().get(part, {})
    rng = p.get("repair" if action == "repair" else "replace_labour") or p.get("replace_labour") or [0, 0]
    return int(rng[0]), int(rng[1])


def paint_range(part: str) -> tuple[int, int]:
    p = parts_catalog().get(part, {}).get("paint")
    return (int(p[0]), int(p[1])) if p else (0, 0)


def estimate_line(*, model: str, part: str, action: str, material: str, vehicle_age_months: int,
                  zero_dep: bool, coverage_status: str) -> dict:
    """Price one damaged part. Returns low/high payable for this line."""
    lab_lo, lab_hi = labour_range(part, action)
    pnt_lo, pnt_hi = paint_range(part)
    price = part_price(model, part) if action == "replace" else None
    part_cost = price["price"] if price else 0
    dep = depreciation_pct(material, vehicle_age_months, zero_dep) if action == "replace" else 0.0
    dep_amt = round(part_cost * dep)
    paint_dep_lo = 0 if zero_dep else round(pnt_lo * PAINT_MATERIAL_SHARE * PAINT_MATERIAL_DEP)
    paint_dep_hi = 0 if zero_dep else round(pnt_hi * PAINT_MATERIAL_SHARE * PAINT_MATERIAL_DEP)

    gross_lo = part_cost + lab_lo + pnt_lo
    gross_hi = part_cost + lab_hi + pnt_hi
    pay_lo = gross_lo - dep_amt - paint_dep_lo
    pay_hi = gross_hi - dep_amt - paint_dep_hi

    factor = {"covered": 1.0, "partial": 0.5, "not_covered": 0.0}.get(coverage_status, 0.0)
    return {
        "part": part,
        "part_name": parts_catalog().get(part, {}).get("name", part),
        "action": action,
        "material": material,
        "part_price": part_cost,
        "part_source_url": price["source_url"] if price else None,
        "price_verified": bool(price and price["verified"]),
        "price_missing": action == "replace" and price is None,
        "labour_low": lab_lo, "labour_high": lab_hi,
        "paint_low": pnt_lo, "paint_high": pnt_hi,
        "dep_pct": dep, "dep_amount": dep_amt,
        "dep_clause": depreciation_clause(material, zero_dep) if action == "replace" else None,
        "paint_dep_low": paint_dep_lo, "paint_dep_high": paint_dep_hi,
        "gross_low": gross_lo, "gross_high": gross_hi,
        "coverage_factor": factor,
        "payable_low": round(pay_lo * factor), "payable_high": round(pay_hi * factor),
    }


def totals(lines: list[dict], cc: int, voluntary_deductible: int = 0) -> dict:
    gross_lo = sum(l["gross_low"] for l in lines)
    gross_hi = sum(l["gross_high"] for l in lines)
    pay_lo = sum(l["payable_low"] for l in lines)
    pay_hi = sum(l["payable_high"] for l in lines)
    ded = compulsory_deductible(cc) + int(voluntary_deductible or 0)
    return {
        "gross_low": gross_lo, "gross_high": gross_hi,
        "not_payable_low": gross_lo - pay_lo, "not_payable_high": gross_hi - pay_hi,
        "compulsory_deductible": compulsory_deductible(cc),
        "voluntary_deductible": int(voluntary_deductible or 0),
        "payable_low": max(0, pay_lo - ded), "payable_high": max(0, pay_hi - ded),
    }
