"""Policy replacement-part rates as fractions, never percentages out of 100.

Age is completed months at the accident date. The caller verifies cover/add-ons.
Paint's 50% rate applies only to material (25% of a consolidated painting bill).
"""
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

RULES = json.loads((Path(__file__).resolve().parents[2] / "data/depreciation.json").read_text())
ALIASES = {"fiber glass": "fibreglass", "fibre glass": "fibreglass", "fiberglass": "fibreglass",
           "tire": "tyres", "tires": "tyres", "tyre": "tyres", "tube": "tubes", "battery": "batteries"}


def depreciation_pct(material: str, vehicle_age_months: int, zero_dep: bool) -> float:
    if type(vehicle_age_months) is not int or vehicle_age_months < 0:
        raise ValueError("vehicle_age_months must be a non-negative integer")
    if type(zero_dep) is not bool:
        raise ValueError("zero_dep must be a boolean, verified against the policy")
    if not isinstance(material, str) or not material.strip():
        raise ValueError("material is required")
    key = material.strip().lower()
    key = ALIASES.get(key, key)
    if key not in RULES["materials"] and key not in {"metal", "steel", "aluminium", "aluminum", "wood", "wooden", "other"}:
        raise ValueError(f"Unclassified material: {material}; confirm material before estimating")
    if zero_dep:
        return 0.0
    if key in RULES["materials"]:
        return RULES["materials"][key]
    return next(b["rate"] for b in RULES["other_parts_age_bands"]
                if b["max_months"] is None or vehicle_age_months <= b["max_months"])


def compulsory_deductible(cc: int) -> int:
    if type(cc) is not int or cc <= 0:
        raise ValueError("cc must be a positive integer")
    rule = RULES["compulsory_deductible"]
    return rule["at_or_below"] if cc <= rule["cc_threshold"] else rule["above"]


def paint_depreciation(paint_bill: float, zero_dep: bool = False, *, material_itemized: bool = False) -> float:
    """Deduct from material only; itemized=True means input already excludes labour."""
    bill = Decimal(str(paint_bill))
    if not bill.is_finite() or bill < 0 or type(zero_dep) is not bool:
        raise ValueError("Expected a non-negative finite bill and boolean zero_dep")
    fraction = Decimal(1) if material_itemized else Decimal(str(RULES["paint_material_fraction_of_consolidated_bill"]))
    amount = bill * fraction * Decimal(str(RULES["materials"]["paint"])) if not zero_dep else Decimal(0)
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
