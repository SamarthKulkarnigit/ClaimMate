from backend.tools import rules


def test_material_depreciation():
    assert rules.depreciation_pct("plastic", 30, False) == 0.5
    assert rules.depreciation_pct("glass", 100, False) == 0.0
    assert rules.depreciation_pct("fibreglass", 1, False) == 0.3


def test_age_depreciation():
    assert rules.depreciation_pct("metal", 5, False) == 0.0
    assert rules.depreciation_pct("metal", 12, False) == 0.05
    assert rules.depreciation_pct("metal", 30, False) == 0.15
    assert rules.depreciation_pct("metal", 64, False) == 0.40
    assert rules.depreciation_pct("metal", 130, False) == 0.50
    assert rules.depreciation_pct("metal", 130, True) == 0.0


def test_deductible():
    assert rules.compulsory_deductible(1197) == 1000
    assert rules.compulsory_deductible(1998) == 2000


def test_not_covered_line_pays_zero():
    l = rules.estimate_line(model="swift", part="front_bumper", action="replace", material="plastic",
                            vehicle_age_months=30, zero_dep=False, coverage_status="not_covered")
    assert l["payable_low"] == 0 and l["gross_low"] > 0
