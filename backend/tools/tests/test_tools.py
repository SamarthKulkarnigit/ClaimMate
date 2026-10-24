import csv
import json
from copy import deepcopy
from pathlib import Path

import imagehash
import pytest
from PIL import Image, ImageOps
from pypdf import PdfReader
from backend.tools import forensics
from backend.tools.claim_pdf import build_claim_pdf
from backend.tools.email_draft import build_email
from backend.tools.prices import part_price, labour_range

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / 'data'

def fixture(name='clean_swift_front'):
    return json.loads((DATA / 'demo_claims' / name / 'expected_state.json').read_text())

def test_nested_exif_and_orientation(tmp_path):
    path = tmp_path / 'photo.jpg'
    im = Image.new('RGB',(80,120),'white')
    for x in range(20):
        for y in range(45): im.putpixel((x,y),(0,0,0))
    exif = Image.Exif(); exif[34665] = {36867:'2026:10:23 12:34:56'}; exif[274] = 6
    im.save(path, exif=exif)
    result = forensics.inspect_photo(str(path))
    assert result['exif_datetime'] == '2026-10-23T12:34:56'
    assert result['has_exif']
    with Image.open(path) as opened:
        assert result['phash'] == str(imagehash.phash(ImageOps.exif_transpose(opened).convert('RGB')))

def test_absent_and_invalid_capture_date(tmp_path):
    path = tmp_path / 'plain.png'
    Image.new('RGB', (30,30)).save(path)
    assert forensics.inspect_photo(str(path))['exif_datetime'] is None
    assert not forensics.inspect_photo(str(path))['has_exif']
    exif = Image.Exif(); exif[306] = 'not a date'
    Image.new('RGB',(30,30)).save(tmp_path/'bad.jpg',exif=exif)
    assert forensics.inspect_photo(str(tmp_path/'bad.jpg'))['exif_datetime'] is None

def test_hash_threshold_and_nearest(tmp_path, monkeypatch):
    path = tmp_path/'index.json'; monkeypatch.setattr(forensics,'HASH_INDEX',path)
    path.write_text(json.dumps([{'claim_id':'near','phash':'000000000000003f'}, {'claim_id':'exact','phash':'0000000000000000'}]))
    assert forensics.find_duplicate('0000000000000000') == 'exact'
    path.write_text(json.dumps([{'claim_id':'six','phash':'000000000000003f'}]))
    assert forensics.find_duplicate('0000000000000000',6) == 'six'
    assert forensics.find_duplicate('0000000000000000',5) is None
    path.write_text('[]'); assert forensics.find_duplicate('0000000000000000') is None
    path.write_text('broken')
    with pytest.raises(json.JSONDecodeError): forensics.find_duplicate('0000000000000000')

@pytest.mark.parametrize('bad', ['', 'bad', 'g'*16, 'a'*15, None])
def test_reject_invalid_hash(bad):
    with pytest.raises(ValueError): forensics.find_duplicate(bad)

def test_photo_dates():
    check = lambda value: forensics.check_photo_date(value, '2026-10-23','2026-01-01','2026-12-31')
    assert check('2026-10-23T10:30:00')['ok'] is True
    assert check('2025-12-31T10:30:00')['action'] == 'escalate'
    assert check('2026-10-24T10:30:00')['action'] == 'request_evidence'
    assert check(None)['ok'] is None
    assert forensics.check_photo_date(None,'2025-10-23','2026-01-01','2026-12-31')['action'] == 'escalate'

def test_prices_and_missing_parts():
    assert part_price('SWIFT','front bumper')['price'] == 2250
    assert part_price('Baleno','tail_lamp')['source_url'].startswith('https://www.marutisuzuki.com/')
    assert part_price('Swift','nonexistent') is None
    assert part_price('other','front_bumper') is None
    assert labour_range('front bumper','replace') == (600,1000)
    with pytest.raises(KeyError): labour_range('engine','repair')

def test_catalogue_provenance():
    rows = list(csv.DictReader((DATA/'prices.csv').open()))
    assert len(rows) >= 20
    assert len({(r['model'],r['part']) for r in rows}) == len(rows)
    for row in rows:
        assert row['checked_on'] == '2026-10-24'
        assert row['source_url'].startswith('https://www.marutisuzuki.com/genuine-parts/')
        assert float(row['price']) > 0 and row['part_number'] and row['fitment_note']

def test_ten_fixtures_inputs_do_not_leak_answers():
    answers = json.loads((DATA/'answer_key.json').read_text())
    assert len(answers) == 10
    for name, answer in answers.items():
        claim = json.loads((DATA/'demo_claims'/name/'claim.json').read_text())
        assert not {'damages','coverage','audit','estimate'} & claim.keys()
        assert answer['synthetic'] and claim['synthetic']
        for photo in claim['photos']:
            result = forensics.inspect_photo(str(ROOT/photo['path']))
            assert result['phash'] == photo['phash']
            assert (forensics.find_duplicate(result['phash']) is not None) == (name == 'duplicate_photo')
        if name == 'exif_before_policy':
            assert forensics.check_photo_date(claim['photos'][0]['exif_datetime'],claim['accident_date'],claim['policy']['start'],claim['policy']['end'])['action'] == 'escalate'

def test_zero_dep_old_metal_and_glass_expectations():
    assert all(l['dep_pct'] == 0 for l in fixture('zero_dep')['estimate']['lines'])
    assert fixture('six_year_old')['estimate']['lines'][0]['dep_pct'] == .4
    assert fixture('windshield_only')['estimate']['lines'][0]['dep_pct'] == 0

def test_pdf_and_email_mask_identifiers_and_escape_markup(tmp_path):
    state = fixture()
    state['story'] = 'TEST0000 & DEMO-POLICY-0001 <b>special</b>'
    dest = tmp_path/'nested'/'report.pdf'
    assert build_claim_pdf(state,str(dest)) == str(dest)
    text = '\n'.join(p.extract_text() for p in PdfReader(dest).pages)
    email = build_email(state)
    for output in [text,email]:
        assert 'TEST0000' not in output and 'DEMO-POLICY-0001' not in output
        assert '2,474.50' in output and '3,074.50' in output
    assert '<b>special</b>' in text
    assert 'SYNTHETIC TEST FIXTURE' in text
    assert 'Section I(vi)' in text and 'marutisuzuki.com' in text
    assert 'DRAFT ONLY' in email

def test_pending_report_and_long_report_paginate(tmp_path):
    path = tmp_path/'empty.pdf'; build_claim_pdf({},str(path))
    text = ''.join(p.extract_text() for p in PdfReader(path).pages)
    assert 'Pending' in text and 'Audit pending' in text
    state = fixture(); line = deepcopy(state['estimate']['lines'][0])
    state['estimate']['lines'] = [line for _ in range(24)]
    build_claim_pdf(state,str(tmp_path/'long.pdf'))
    assert len(PdfReader(tmp_path/'long.pdf').pages) > 2
