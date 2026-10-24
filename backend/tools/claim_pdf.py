"""ReportLab claim assessment, with source references and masked identifiers."""
from pathlib import Path
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

from .email_draft import mask, redact


def build_claim_pdf(state: dict, out_path: str) -> str:
    """Write a review document; no insurer approval/submission is implied."""
    destination = Path(out_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SmallText", fontSize=8, leading=12, textColor=colors.HexColor("#4b586b")))
    styles.add(ParagraphStyle(name="Money", parent=styles["SmallText"], alignment=TA_RIGHT))
    styles["Title"].textColor = colors.HexColor("#162c48")
    styles["Heading2"].textColor = colors.HexColor("#136b60")
    styles["BodyText"].leading = 14

    def p(value, style="BodyText"):
        # Standard PDF fonts are Latin-1. INR is used instead of a missing rupee glyph.
        text = redact(value, state).replace("₹", "INR ").replace("—", " - ").replace("–", "-")
        text = text.encode("latin-1", "replace").decode("latin-1")
        return Paragraph(escape(text).replace("\n", "<br/>"), styles[style])

    def money(value):
        return "Pending" if value is None else f"INR {float(value):,.2f}"

    def table(rows, widths, header=True):
        result = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        commands = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LINEBELOW", (0, 0), (-1, -1), .3, colors.HexColor("#dce3e9"))]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f2ef"))]
        result.setStyle(TableStyle(commands))
        return result

    vehicle, policy = state.get("vehicle", {}), state.get("policy", {})
    estimate, audit = state.get("estimate", {}), state.get("audit", {})
    totals = estimate.get("totals", {})
    content = [p("CLAIMMATE / MOTOR OWN DAMAGE", "SmallText"), Spacer(1, 4*mm),
               p("Claim assessment", "Title"),
               p("ESTIMATE FOR REVIEW - not a settlement or proof of insurer approval", "SmallText"), Spacer(1, 5*mm)]
    if state.get("synthetic"):
        content += [p("SYNTHETIC TEST FIXTURE - simulated assessment; not real damage evidence.", "Heading2")]
    details = [("Claim", state.get("claim_id", "Pending")),
               ("Vehicle", f"{vehicle.get('make', '')} {vehicle.get('model', '')} / {mask(vehicle.get('reg_no'))}"),
               ("Policy", f"{mask(policy.get('policy_no'))} | {policy.get('start', '?')} to {policy.get('end', '?')}"),
               ("Accident date", state.get("accident_date", "Not supplied")),
               ("Review", f"Audit: {audit.get('status', 'pending')} | Decision: {state.get('decision') or 'pending'}")]
    content += [table([[p(k, "SmallText"), p(v)] for k, v in details], [35*mm, 139*mm], False),
                Spacer(1, 4*mm), p("Incident", "Heading2"), p(state.get("story", "Not supplied")),
                p("Estimated payout", "Heading2")]
    rows = [[p(x, "SmallText") for x in ("Part / action", "Parts price", "Labour range", "Depreciation", "Payable range")]]
    for line in estimate.get("lines", []):
        rows.append([p(f"{line.get('part', '?')} / {line.get('action', '?')}\n{line.get('clause_id', 'Citation pending')}", "SmallText"),
                     p(money(line.get("part_price")), "Money"),
                     p(f"{money(line.get('labour_low'))}\nto {money(line.get('labour_high'))}", "Money"),
                     p(f"{float(line.get('dep_pct', 0))*100:g}%\n{money(line.get('dep_amount'))}", "Money"),
                     p(f"{money(line.get('payable_low'))}\nto {money(line.get('payable_high'))}", "Money")])
    content.append(table(rows, [44*mm, 28*mm, 34*mm, 30*mm, 38*mm]) if len(rows) > 1 else p("Assessment pending."))
    content += [Spacer(1, 4*mm), p(f"Gross: {money(totals.get('gross_low'))} - {money(totals.get('gross_high'))}\n"
                f"Depreciation: {money(totals.get('depreciation'))} | Deductible: {money(totals.get('deductible'))}\n"
                f"Estimated payable: {money(totals.get('payable_low'))} - {money(totals.get('payable_high'))}"),
                p("Labour rates are assumptions. Catalogue fitment, policy endorsements and final admissibility require verification. "
                  "Line payable amounts are before the claim-level deductible.", "SmallText"), p("Coverage & evidence references", "Heading2")]
    coverage = {row.get("part"): row for row in state.get("coverage", [])}
    for index, line in enumerate(estimate.get("lines", []), 1):
        cov = coverage.get(line.get("part"), {})
        block = [p(f"{index}. {line.get('part')} | {line.get('clause_id', 'Citation pending')}", "Heading3"),
                 p(f"Evidence: {', '.join(line.get('photo_ids', [])) or 'Missing'} | Coverage: {cov.get('status', 'pending')}", "SmallText")]
        if cov.get("clause_quote"):
            block.append(p(f"Policy excerpt: {cov['clause_quote']}", "SmallText"))
        if cov.get("reason"):
            block.append(p(cov["reason"], "SmallText"))
        if line.get("note"):
            block.append(p(line["note"], "SmallText"))
        url = line.get("part_source_url", "")
        if urlparse(url).scheme in {"https", "http"}:
            block.append(Paragraph(f'<link href="{escape(url, {chr(34): "&quot;"})}" color="#136b60">Parts source: {escape(url)}</link>', styles["SmallText"]))
        content.append(KeepTogether(block))
    for cov in state.get("coverage", []):
        if cov.get("status") != "covered":
            content += [p(f"{cov.get('part')}: {cov.get('status')} / {cov.get('clause_id', 'Citation pending')}", "Heading3"),
                        p(cov.get("reason", "Review required."), "SmallText")]
    content.append(p("Auditor findings", "Heading2"))
    for finding in audit.get("findings", []):
        label = "PASS" if finding.get("ok") is True else "REVIEW"
        content.append(p(f"{finding.get('check', '?')} / {label}: {finding.get('detail', '')}", "SmallText"))
    if not audit.get("findings"):
        content.append(p("Audit pending. No checks have been represented as passed.", "SmallText"))
    content += [p("Policy source", "Heading2"), p("Royal Sundaram Stand-Alone Motor Own Damage Policy - Private Car, Rev 2023. "
                "Section I: accidental external means, replacement-part depreciation and exclusions.", "SmallText"),
                p("https://www.royalsundaram.in/assets/standalone-motor-own-damage-policy-private-car-rev2023.pdf", "SmallText")]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#697586"))
        canvas.drawString(18*mm, 12*mm, "ClaimMate | Estimate for review | Identifiers masked")
        canvas.drawRightString(A4[0]-18*mm, 12*mm, f"Page {doc.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(str(destination), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                                topMargin=16*mm, bottomMargin=22*mm, title="ClaimMate claim assessment")
    document.build(content, onFirstPage=footer, onLaterPages=footer)
    return str(destination)
