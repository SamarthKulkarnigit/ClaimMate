"""Regenerate synthetic fixtures, UI replays, and sample PDF. No model evaluation.

Run from repo root: .venv/bin/python -m data.generate_fixtures
Only writes under data/demo_claims, data/answer_key.json, data/labour.json,
data/past_claims_hashes.json and frontend/public/demo.
"""
import csv
import json
import random
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from backend.tools.depreciation import depreciation_pct, compulsory_deductible
from backend.tools.prices import part_price
from backend.tools.forensics import inspect_photo
from backend.tools.claim_pdf import build_claim_pdf
from backend.tools.email_draft import build_email

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
PUBLIC = ROOT / 'frontend/public/demo'
NAMES = ['clean_swift_front', 'partial_baleno_rear', 'mismatch_front_rear', 'duplicate_photo',
         'exif_before_policy', 'plate_mismatch', 'blurry_photo', 'zero_dep', 'six_year_old', 'windshield_only']
TITLES = ['A straightforward claim', 'A closer look at coverage', 'When the story does not match',
          'A reused photo', 'Outside the policy period', 'A different number plate',
          'More evidence needed', 'With zero depreciation', 'A six-year-old vehicle', 'Windshield damage only']


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + '\n')


def picture(path, index, parts, captured='2026:10:23 10:30:00'):
    rng = random.Random(426 + index)
    img = Image.new('RGB', (1000, 620), '#dfe9ed')
    d = ImageDraw.Draw(img)
    # Distinct seeded test patterns exercise pHash without pretending to be photographs.
    for _ in range(22):
        x, y = rng.randrange(1000), rng.randrange(550)
        d.ellipse((x, y, x+rng.randrange(60, 260), y+rng.randrange(60, 200)), fill=rng.choice(['#a7c1cb', '#b0c8c0', '#cad6dd', '#edf0e8']))
    d.rounded_rectangle((220, 235, 780, 490), 70, fill='#6a899e', outline='#334f68', width=5)
    d.polygon([(325, 155), (675, 155), (740, 285), (260, 285)], fill='#8aa7b9', outline='#334f68')
    d.polygon([(340, 175), (660, 175), (700, 260), (300, 260)], fill='#dbeef1')
    d.rounded_rectangle((240, 330, 365, 385), 12, fill='#fff2bd')
    d.rounded_rectangle((635, 330, 760, 385), 12, fill='#fff2bd')
    d.rectangle((365, 345, 635, 375), fill='#29435a')
    d.rounded_rectangle((260, 420, 740, 465), 15, fill='#49667b')
    d.rounded_rectangle((405, 390, 595, 425), 4, fill='#f7f9fa')
    d.text((420, 399), 'TEST / 0000', fill='#29435a', font=ImageFont.load_default(size=22))
    for x, y in ([(290, 435), (680, 350)] if 'windshield' not in parts else [(440, 210)]):
        d.ellipse((x-47, y-47, x+47, y+47), outline='#de6953', width=5)
        d.line([(x-23, y-24), (x+12, y-5), (x-12, y+18), (x+28, y+26)], fill='#de6953', width=6)
    if index == 6:
        img = img.filter(ImageFilter.GaussianBlur(18)); d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 1000, 64), fill='#17344d')
    d.text((25, 20), 'SYNTHETIC TEST DIAGRAM / NOT A DAMAGE PHOTO', font=ImageFont.load_default(size=25), fill='white')
    d.rectangle((0, 550, 1000, 620), fill='#f2f6f8')
    d.text((25, 574), 'Expected tags: ' + ', '.join(parts), font=ImageFont.load_default(size=22), fill='#17344d')
    exif = Image.Exif()
    exif[34665] = {36867: captured}
    img.save(path, quality=92, exif=exif)


def generate():
    PUBLIC.mkdir(parents=True, exist_ok=True)
    catalogue = list(csv.DictReader((DATA / 'prices.csv').open()))
    labour = {}
    for row in catalogue:
        part = row['part']
        if 'bumper' in part or 'fender' in part:
            labour[part] = {'repair': [900, 1500], 'replace': [600, 1000], 'paint': [1800, 2600]}
        elif 'glass' in part or 'windshield' in part:
            labour[part] = {'replace': [700, 1200]}
        else:
            labour[part] = {'replace': [250, 450]}
    write(DATA / 'labour.json', labour)
    answers, manifest = {}, []
    duplicate_hash = None
    for i, name in enumerate(NAMES):
        directory = DATA / 'demo_claims' / name
        (directory / 'photos').mkdir(parents=True, exist_ok=True)
        model = 'Baleno' if i == 1 else 'Swift'
        parts = ['rear_bumper', 'tail_lamp'] if i == 1 else ['front_bumper', 'headlamp']
        if i == 8: parts = ['front_fender_right']
        if i == 9: parts = ['windshield']
        photo = directory / 'photos/evidence.jpg'
        picture(photo, i, parts, '2025:01:03 10:30:00' if i == 4 else '2026:10:23 10:30:00')
        inspected = inspect_photo(str(photo))
        if i == 3: duplicate_hash = inspected['phash']
        story = 'Hit a pole while parking; front bumper and right headlamp were damaged.'
        if i == 1: story = 'A low-speed rear impact damaged my bumper and left tail lamp. I also reported engine noise.'
        if i == 2: story = 'I was rear-ended while stopped at a traffic signal.'
        if i == 8: story = 'A parking scrape damaged the right front fender.'
        if i == 9: story = 'A flying stone cracked my windshield.'
        claim = {'claim_id': f'DEMO-{i+1:03}', 'synthetic': True, 'story': story, 'accident_date': '2026-10-23',
                 'vehicle': {'make': 'Maruti Suzuki', 'model': model, 'reg_no': 'TEST0000', 'cc': 1197,
                             'reg_date': '2020-10-23' if i == 8 else '2024-04-23', 'age_months': 72 if i == 8 else 30},
                 'policy': {'policy_no': 'DEMO-POLICY-0001', 'start': '2026-01-01', 'end': '2026-12-31', 'idv': 500000,
                            'zero_dep': i == 7, 'voluntary_deductible': 0, 'pdf_path': 'data/policy/standard_od_policy.pdf'},
                 'photos': [{'id': 'photo-1', 'path': str(photo.relative_to(ROOT)), **inspected}]}
        # Inputs contain no expected outputs. The answer key is separate from claim.json.
        write(directory / 'claim.json', claim)
        damages, lines, coverage = [], [], []
        for part in parts:
            price = part_price(model, part)
            assert price, (model, part)
            pct = depreciation_pct(price['material'], claim['vehicle']['age_months'], i == 7)
            low, high = labour[part]['replace']
            dep = round(price['price'] * pct, 2)
            damages.append({'part': part, 'side': 'rear' if i == 1 else 'front', 'severity': 'moderate', 'action': 'replace',
                            'material': price['material'], 'photo_ids': ['photo-1'], 'confidence': 0.35 if i == 6 else 0.94})
            coverage.append({'part': part, 'status': 'covered', 'clause_id': 'Section I(vi)',
                             'clause_quote': 'by accidental external means;', 'reason': 'Synthetic scenario assumes admissible accidental external damage.'})
            lines.append({'part': part, 'action': 'replace', 'part_price': price['price'], 'part_source_url': price['source_url'],
                          'labour_low': low, 'labour_high': high, 'paint': 0, 'material': price['material'], 'dep_pct': pct, 'dep_amount': dep,
                          'payable_low': round(price['price']-dep+low, 2), 'payable_high': round(price['price']-dep+high, 2),
                          'clause_id': 'Section I(vi)', 'photo_ids': ['photo-1'],
                          'note': f"Labour is an assumption; painting excluded from this fixture. {price['fitment_note']}"})
        if i == 1:
            coverage.append({'part': 'engine_noise', 'status': 'not_covered', 'clause_id': 'Section I - exclusion (a)', 'clause_quote': '',
                             'reason': 'Fixture assumption: inspection attributes engine noise to pre-existing mechanical breakdown, not the impact. Real causation requires a surveyor.'})
        failing_check = {2: 'A4', 3: 'A2', 4: 'A1', 5: 'A3', 6: 'A6'}.get(i)
        audit_status = 'escalate' if failing_check else 'pass'
        details = {'A1': 'Capture date matches the accident date and policy period.', 'A2': 'No matching image in the prior-claim fixture index.',
                   'A3': 'Fixture plate matches the supplied vehicle record.', 'A4': 'Incident location agrees with the fixture damage labels.',
                   'A5': 'Each estimate line has evidence and a coverage decision.', 'A6': 'Fixture confidence is above 0.6; no structural damage is specified.'}
        if failing_check:
            details[failing_check] = {2: 'Story says rear-ended; fixture evidence shows front damage. Two re-checks did not resolve the mismatch.',
                3: 'Perceptual hash matches SYNTHETIC-PAST-001. Review required; similarity alone is not proof of fraud.',
                4: 'Photo capture date precedes the policy start date.', 5: 'Fixture plate TEST9999 differs from the vehicle record after re-check.',
                6: 'Evidence is blurred; confidence 0.35. Request clearer photos and refer to a surveyor.'}[i]
        findings = [{'check': key, 'ok': key != failing_check, 'detail': value} for key, value in details.items()]
        deductible = compulsory_deductible(claim['vehicle']['cc'])
        totals = {'gross_low': sum(l['part_price']+l['labour_low'] for l in lines), 'gross_high': sum(l['part_price']+l['labour_high'] for l in lines),
                  'depreciation': sum(l['dep_amount'] for l in lines), 'deductible': deductible,
                  'payable_low': max(0, sum(l['payable_low'] for l in lines)-deductible), 'payable_high': max(0, sum(l['payable_high'] for l in lines)-deductible)}
        final = {**claim, 'damages': damages, 'coverage': coverage, 'estimate': {'lines': lines, 'totals': totals},
                 'audit': {'status': audit_status, 'findings': findings}, 'plate_read': 'TEST9999' if i == 5 else 'TEST0000',
                 'retries': 2 if i == 2 else 1 if i == 5 else 0, 'next': 'surveyor' if failing_check else 'human', 'decision': None}
        write(directory / 'expected_state.json', final)
        answers[name] = {'covered_parts': parts, 'not_covered_parts': ['engine_noise'] if i == 1 else [], 'expected_audit_outcome': audit_status,
                         'expected_failed_checks': [failing_check] if failing_check else [], 'expected_retries': final['retries'],
                         'expected_dep_pct': {l['part']: l['dep_pct'] for l in lines}, 'synthetic': True,
                         'evaluation_note': 'Expected labels for a controlled fixture; not measured model accuracy.'}
        if i < 3:
            manifest.append({'name': name, 'title': TITLES[i], 'description': ['Swift · front damage · review & approve', 'Baleno · partial coverage · mechanical exclusion', 'Swift · story mismatch · two retries & escalation'][i]})
            shutil.copyfile(photo, PUBLIC / f'{name}.jpg')
            final['photos'][0]['url'] = f'/demo/{name}.jpg'
            events = []
            def event(kind, agent, text, data=None):
                events.append({'type': kind, 'agent': agent, 'ts': f'2026-10-24T05:30:{len(events):02}Z', 'text': text, 'data': data or {}})
            for agent, msg in [('intake', 'Photo metadata and duplicate signals collected.'), ('coordinator', 'Routing the evidence for assessment.'),
                               ('damage', 'Fixture damage tags added.'), ('policy', 'Coverage decisions linked to policy references.'), ('cost', 'Estimate calculated from the catalogue and fixed rules.'), ('auditor', 'Running six consistency checks.')]:
                event('agent_start', agent, msg)
                event('agent_end', agent, agent.title() + ' complete.')
            if i == 2:
                for retry in (1, 2):
                    event('send_back', 'auditor', 'Story says rear impact; evidence is at the front. Re-check the damage location.', {'retries': retry, 'send_back_to': 'damage'})
                    event('agent_start', 'coordinator', 'Routing Auditor feedback to Damage Assessor.')
                    event('agent_end', 'coordinator', 'Re-check requested.')
                    event('agent_start', 'damage', 'Re-checking location against the story.')
                    event('agent_end', 'damage', 'Front damage remains confirmed by the fixture.')
                    event('agent_start', 'auditor', 'Reviewing the updated assessment.')
                event('escalate', 'auditor', 'Mismatch unresolved after two send-backs. Human surveyor required.')
            else:
                event('interrupt', 'human', 'Checks complete. Your review is required before preparing the claim file.')
            write(PUBLIC / f'{name}.json', {'input': claim, 'state': final, 'events': events})
            approved = {**final, 'decision': 'approved'}
            # Public samples are explicitly synthetic; production PDFs come from the API.
            build_claim_pdf(approved if i != 2 else final, str(PUBLIC / f'{name}.pdf'))
            (PUBLIC / f'{name}.txt').write_text(build_email(approved if i != 2 else final))
    write(DATA / 'answer_key.json', answers)
    write(DATA / 'past_claims_hashes.json', [{'claim_id': 'SYNTHETIC-PAST-001', 'phash': duplicate_hash}])
    write(PUBLIC / 'manifest.json', manifest)
    print(f'Generated {len(answers)} synthetic fixtures and {len(manifest)} browser replays.')

if __name__ == '__main__':
    generate()
