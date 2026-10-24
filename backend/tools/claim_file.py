"""Claim-file PDF and insurer email draft. Personal IDs are masked."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend import config
from backend.tools.email_draft import redact

POLICY_SOURCE = "https://www.royalsundaram.in/assets/standalone-motor-own-damage-policy-private-car-rev2023.pdf"


def mask(s: str | None, keep: int = 4) -> str:
    s = s or ""
    return "•" * max(0, len(s) - keep) + s[-keep:] if s else "-"


def rs(n) -> str:
    return f"Rs {int(n or 0):,}"


def _t(value, state: dict) -> str:
    """User/LLM text for a ReportLab Paragraph: identifiers masked, markup escaped."""
    return escape(redact(value or "", state))


def build_pdf(state: dict, status: str) -> Path:
    out = config.OUTPUTS / f"{state['claim_id']}.pdf"
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=8, leading=10)
    v, pol = state.get("vehicle") or {}, state.get("policy") or {}
    est = state.get("estimate") or {}
    t = est.get("totals") or {}
    el = []

    el.append(Paragraph("ClaimMate — Motor Own-Damage Claim File", ss["Title"]))
    el.append(Paragraph(f"<b>Status:</b> {status} &nbsp;&nbsp; <b>Claim ID:</b> {state['claim_id']} &nbsp;&nbsp; "
                        f"<b>Generated:</b> {datetime.now():%d %b %Y %H:%M}", ss["BodyText"]))
    el.append(Paragraph("ESTIMATE FOR REVIEW - not a settlement or proof of insurer approval.", small))
    if state.get("synthetic"):
        el.append(Paragraph("<b>SYNTHETIC TEST FIXTURE</b> - test diagram and scripted inputs; not real damage evidence.",
                            ss["BodyText"].clone("synthetic", textColor=colors.HexColor("#b45309"))))
    el.append(Spacer(1, 4 * mm))

    info = [["Vehicle", f"{v.get('make', '')} {v.get('model', '')}".strip(), "Reg. no.", mask(v.get("reg_no"))],
            ["Engine", f"{v.get('cc', '-')} cc", "Vehicle age", f"{v.get('age_months', '-')} months"],
            ["Policy no.", mask(pol.get("policy_no")), "Period", f"{pol.get('start', '-')} to {pol.get('end', '-')}"],
            ["Accident date", state.get("accident_date", "-"), "Zero-dep add-on", "Yes" if pol.get("zero_dep") else "No"]]
    ti = Table(info, colWidths=[28 * mm, 60 * mm, 30 * mm, 55 * mm])
    ti.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                            ("TEXTCOLOR", (2, 0), (2, -1), colors.grey)]))
    el += [ti, Spacer(1, 3 * mm), Paragraph(f"<b>Owner's account:</b> {_t(state.get('story'), state)}", ss["BodyText"]),
           Spacer(1, 4 * mm)]

    if est.get("lines"):
        el.append(Paragraph("Estimate (every line cites a policy clause and photo)", ss["Heading3"]))
        rows = [["Part", "Action", "Cover", "Clause", "Dep.", "Payable (range)", "Photos"]]
        cov = {c["part"]: c for c in state.get("coverage") or []}
        for l in est["lines"]:
            rows.append([l["part_name"], l["action"], cov.get(l["part"], {}).get("status", "-"),
                         l.get("clause_id") or "-", f"{int(l['dep_pct'] * 100)}%",
                         f"{rs(l['payable_low'])} – {rs(l['payable_high'])}", ", ".join(l.get("photo_ids", []))])
        tb = Table(rows, repeatRows=1)
        tb.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)]))
        el.append(tb)
        el.append(Spacer(1, 3 * mm))
        tot = [["Gross repair estimate", f"{rs(t.get('gross_low'))} – {rs(t.get('gross_high'))}"],
               ["Not payable (depreciation / exclusions)", f"{rs(t.get('not_payable_low'))} – {rs(t.get('not_payable_high'))}"],
               ["Compulsory deductible (IMT.22)", rs(t.get("compulsory_deductible"))],
               ["Voluntary deductible", rs(t.get("voluntary_deductible"))],
               ["EXPECTED PAYOUT (estimate)", f"{rs(t.get('payable_low'))} – {rs(t.get('payable_high'))}"]]
        tt = Table(tot, colWidths=[90 * mm, 70 * mm])
        tt.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                                ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black)]))
        el.append(tt)

        el.append(Paragraph("Policy references and price sources", ss["Heading3"]))
        for l in est["lines"]:
            c = cov.get(l["part"], {})
            el.append(Paragraph(f"<b>{escape(l['part_name'])}</b> [{escape(c.get('clause_id') or '-')}] {_t(c.get('reason'), state)}", small))
            if c.get("clause_quote"):
                el.append(Paragraph(f"Policy text (unverified against the PDF): <i>{_t(c['clause_quote'], state)}</i>", small))
            url = l.get("part_source_url") or ""
            if urlparse(url).scheme in ("http", "https"):
                el.append(Paragraph(f'Parts price source: <link href="{escape(url, {chr(34): "&quot;"})}" color="#136b60">'
                                    f'{escape(url)}</link>', small))
            elif l["action"] == "replace":
                el.append(Paragraph("Parts price: no catalogue source - garage quote needed.", small))

    extras = state.get("extra_items") or []
    if extras:
        el.append(Spacer(1, 3 * mm))
        el.append(Paragraph("Other items mentioned", ss["Heading3"]))
        for x in extras:
            el.append(Paragraph(f"• {_t(x.get('item'), state)}: <b>{escape(x['status'])}</b> [{escape(x.get('clause_id') or '-')}] — "
                                f"{_t(x.get('reason'), state)}", small))

    audit = state.get("audit") or {}
    if audit.get("findings"):
        el.append(Spacer(1, 3 * mm))
        el.append(Paragraph(f"Auditor checks — {audit.get('status', '').upper()}", ss["Heading3"]))
        for x in audit["findings"]:
            tag = "PASS" if x["ok"] else ("NOTE" if x["ok"] is None else "FLAG")
            el.append(Paragraph(f"{tag} · {escape(x['check'])} {escape(x.get('name', ''))}: {_t(x['detail'], state)}", small))

    if state.get("escalation"):
        el.append(Spacer(1, 3 * mm))
        el.append(Paragraph("Handed over to a human surveyor because: " + "; ".join(_t(r, state) for r in state["escalation"]["reasons"]), ss["BodyText"]))

    imgs = [Image(p["path"], width=40 * mm, height=30 * mm) for p in (state.get("photos") or [])[:4]
            if Path(p["path"]).exists()]
    if imgs:
        el += [Spacer(1, 3 * mm), KeepTogether([Paragraph("Evidence photos", ss["Heading3"]), Table([imgs])])]

    el += [Spacer(1, 5 * mm), Paragraph(
        "All amounts are ESTIMATES from catalogue prices, assumed labour rates and the standard depreciation schedule. "
        "Final settlement is decided by the insurer's surveyor. Labour/paint ranges are assumptions; parts marked "
        "unverified need a catalogue/garage price.", small),
        Paragraph(f"Policy source: Royal Sundaram Stand-Alone Motor Own Damage Policy - Private Car, Rev 2023. {POLICY_SOURCE}", small)]
    SimpleDocTemplate(str(out), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                      topMargin=12 * mm, bottomMargin=12 * mm).build(el)
    return out


def build_email(state: dict) -> str:
    v, pol = state.get("vehicle") or {}, state.get("policy") or {}
    t = (state.get("estimate") or {}).get("totals") or {}
    parts = ", ".join(l["part_name"] for l in (state.get("estimate") or {}).get("lines", []))
    synthetic = "SYNTHETIC TEST FIXTURE - not a real claim.\n\n" if state.get("synthetic") else ""
    return redact(
        f"Subject: Own-damage claim intimation — Policy {mask(pol.get('policy_no'))} — Vehicle {mask(v.get('reg_no'))}\n\n"
        f"{synthetic}Dear Claims Team,\n\n"
        f"I am writing to intimate an own-damage claim under the above policy (Condition 1 — notice of claim).\n\n"
        f"Date of accident: {state.get('accident_date')}\n"
        f"What happened: {state.get('story')}\n"
        f"Damaged parts: {parts or 'see attached'}\n"
        f"Estimated repair (pre-survey): {rs(t.get('gross_low'))} – {rs(t.get('gross_high'))}\n"
        f"Estimated payable after depreciation and deductibles: {rs(t.get('payable_low'))} – {rs(t.get('payable_high'))}\n\n"
        f"Attached: claim file with photos, clause-wise estimate and pre-checks (ClaimMate ref {state['claim_id']}).\n"
        f"Please arrange a survey at the earliest. I can be reached on the registered mobile number.\n\n"
        f"Regards,\nPolicyholder\n\n"
        f"DRAFT ONLY - not sent. Amounts are estimates; final settlement follows the insurer's survey.",
        state)
