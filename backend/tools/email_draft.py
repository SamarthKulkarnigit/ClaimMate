"""Build a draft only; this module never sends email."""


def mask(value) -> str:
    text = str(value or "")
    return "*" * max(4, len(text) - 4) + text[-4:] if len(text) > 4 else "****"


def redact(text, state: dict) -> str:
    result = str(text or "")
    for value in ((state.get("vehicle") or {}).get("reg_no"), (state.get("policy") or {}).get("policy_no")):
        if value:
            result = result.replace(str(value), mask(value))
    return result


def build_email(state: dict) -> str:
    vehicle, policy = state.get("vehicle", {}), state.get("policy", {})
    totals = state.get("estimate", {}).get("totals", {})
    amount = (f"INR {totals['payable_low']:,.2f} - {totals['payable_high']:,.2f} (estimate)"
              if "payable_low" in totals and "payable_high" in totals else "Pending assessment")
    synthetic = "SYNTHETIC TEST FIXTURE - not a real claim.\n\n" if state.get("synthetic") else ""
    return redact(f"""Subject: Motor own damage claim review - {state.get('claim_id', 'Pending')}

{synthetic}Dear Claims Team,

Please review the attached claim assessment and supporting evidence.
Vehicle: {vehicle.get('make', '')} {vehicle.get('model', '')} / {mask(vehicle.get('reg_no'))}
Policy: {mask(policy.get('policy_no'))}
Accident date: {state.get('accident_date', 'Not supplied')}
Incident: {state.get('story', 'Not supplied')}
Estimated payable: {amount}
Audit: {state.get('audit', {}).get('status', 'pending')}
Review decision: {state.get('decision') or 'pending'}

The range uses source-linked parts prices and assumed labour rates. Coverage,
fitment, add-ons and the final settlement remain subject to insurer verification.
Please advise on the required documents and surveyor appointment, if applicable.

Regards,
Policyholder

DRAFT ONLY - not sent. Full identifiers should be supplied through the insurer's secure channel.
""", state)
