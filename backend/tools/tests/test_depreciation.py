import pytest
from backend.tools.depreciation import depreciation_pct, compulsory_deductible, paint_depreciation

@pytest.mark.parametrize('months,expected', [(0,0),(6,0),(7,.05),(12,.05),(13,.1),(24,.1),(25,.15),(36,.15),(37,.25),(48,.25),(49,.35),(60,.35),(61,.4),(120,.4),(121,.5)])
def test_age_boundary(months, expected):
    assert depreciation_pct('metal', months, False) == expected

@pytest.mark.parametrize('material,expected', [('plastic',.5),('rubber',.5),('nylon',.5),('tyre',.5),('tire',.5),('tube',.5),('battery',.5),('fibreglass',.3),('fiber glass',.3),('glass',0),('wood',.15),('paint',.5)])
def test_materials_and_zero_dep(material, expected):
    assert depreciation_pct(material, 30, False) == expected
    assert depreciation_pct(material, 30, True) == 0

@pytest.mark.parametrize('age', [-1, 1.2, True, '30'])
def test_invalid_age(age):
    with pytest.raises(ValueError): depreciation_pct('metal', age, False)

@pytest.mark.parametrize('material', ['', 'unknown', 'mixed'])
def test_unclassified_material_is_not_silently_metal(material):
    with pytest.raises(ValueError): depreciation_pct(material, 30, False)

@pytest.mark.parametrize('cc,expected', [(1,1000),(1197,1000),(1500,1000),(1501,2000),(2000,2000)])
def test_deductible(cc, expected):
    assert compulsory_deductible(cc) == expected

@pytest.mark.parametrize('cc', [0,-1,True,'1500',1500.5])
def test_invalid_capacity(cc):
    with pytest.raises(ValueError): compulsory_deductible(cc)

def test_paint_material_only():
    assert paint_depreciation(4000) == 500
    assert paint_depreciation(1000, material_itemized=True) == 500
    assert paint_depreciation(4000, True) == 0
    assert paint_depreciation(10.04) == 1.26

@pytest.mark.parametrize('amount', [-1, float('inf'), float('nan')])
def test_bad_paint_amount(amount):
    with pytest.raises(ValueError): paint_depreciation(amount)

def test_zero_dep_requires_bool():
    with pytest.raises(ValueError): depreciation_pct('plastic', 30, 'false')
