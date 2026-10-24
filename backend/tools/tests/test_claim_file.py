"""Live-flow claim file (backend.tools.claim_file) used by the finalize/escalate nodes."""
import pytest
from pypdf import PdfReader

from backend import config
from backend.tools import claim_file


def state(**extra):
    base = {'claim_id': 'CLM-TEST', 'story': 'Hit a pole <b>bumper & lamp; reg TEST000000',
            'accident_date': '2026-10-23', 'synthetic': True,
            'vehicle': {'make': 'Maruti Suzuki', 'model': 'Swift', 'reg_no': 'TEST000000', 'cc': 1197, 'age_months': 30},
            'policy': {'policy_no': 'POLICY-TEST-0001', 'start': '2026-01-01', 'end': '2026-12-31', 'zero_dep': False},
            'coverage': [{'part': 'front_bumper', 'status': 'covered', 'clause_id': 'S1.PERIL.vi',
                          'reason': 'Accidental <damage> & impact.', 'clause_quote': 'by accidental external means.'}],
            'extra_items': [{'item': 'engine <noise>', 'status': 'not_covered', 'clause_id': 'S1.EXCL.a', 'reason': 'A & B'}],
            'estimate': {'lines': [
                {'part': 'front_bumper', 'part_name': 'Front bumper', 'action': 'replace', 'dep_pct': 0.5,
                 'payable_low': 3300, 'payable_high': 4400, 'photo_ids': ['P1'], 'clause_id': 'S1.PERIL.vi',
                 'part_source_url': 'https://www.marutisuzuki.com/genuine-parts/front-bumper/71711m55r00-5pk'},
                {'part': 'tail_lamp', 'part_name': 'Tail lamp', 'action': 'replace', 'dep_pct': 0.5,
                 'payable_low': 0, 'payable_high': 0, 'photo_ids': ['P1'], 'clause_id': 'S1.PERIL.vi', 'part_source_url': None}],
                'totals': {'gross_low': 7899, 'gross_high': 9299, 'payable_low': 4049, 'payable_high': 5349,
                           'compulsory_deductible': 1000, 'voluntary_deductible': 0}},
            'audit': {'status': 'pass', 'findings': [{'check': 'A4', 'name': 'story', 'ok': True, 'detail': 'x < y & z'}]},
            'photos': []}
    return {**base, **extra}


@pytest.fixture(autouse=True)
def outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'OUTPUTS', tmp_path)


def text_of(path):
    return ' '.join(page.extract_text() for page in PdfReader(str(path)).pages)


def test_pdf_escapes_markup_and_masks_identifiers():
    text = text_of(claim_file.build_pdf(state(escalation={'reasons': ['Photo <old> & reused']}), 'ESCALATED'))
    assert '<b>bumper & lamp' in text and 'engine <noise>' in text and 'Photo <old> & reused' in text
    assert 'TEST000000' not in text and 'POLICY-TEST-0001' not in text


def test_pdf_labels_synthetic_estimate_sources_and_missing_prices():
    text = text_of(claim_file.build_pdf(state(), 'READY TO FILE'))
    assert 'SYNTHETIC TEST FIXTURE' in text and 'ESTIMATE FOR REVIEW' in text
    assert 'marutisuzuki.com/genuine-parts/front-bumper' in text
    assert 'garage quote needed' in text and 'unverified against the PDF' in text
    assert 'SYNTHETIC' not in text_of(claim_file.build_pdf(state(synthetic=False), 'READY TO FILE'))


def test_email_is_masked_labelled_draft():
    email = claim_file.build_email(state())
    assert 'TEST000000' not in email and 'POLICY-TEST-0001' not in email
    assert email.startswith('Subject:') and 'SYNTHETIC TEST FIXTURE' in email
    assert 'DRAFT ONLY - not sent' in email and 'Rs 4,049' in email
    assert 'SYNTHETIC' not in claim_file.build_email(state(synthetic=False))


def test_escalation_email_lists_reasons_and_stays_a_masked_draft():
    email = claim_file.build_email(state(), escalation_reasons=['Plate TEST000000 differs from RC'])
    assert "flagged the following for your surveyor's inspection" in email
    assert 'TEST000000' not in email and 'DRAFT ONLY - not sent' in email
    no_totals = state(estimate={'lines': [], 'totals': {}})
    pending = claim_file.build_email(no_totals, escalation_reasons=['No damage detected'])
    assert 'Rs 0' not in pending and 'pending surveyor inspection' in pending
