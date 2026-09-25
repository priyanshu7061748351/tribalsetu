"""
Multi-Criteria AI Trust Scoring Module
Advisory document-screening signals for human review.
The output is not a scheme eligibility decision, fraud finding, or approval.
"""

def compute_composite_trust_score(
    qr_result: dict,
    ela_result: dict,
    identity_result: dict,
    gazette_result: dict,
    dbt_result: dict
) -> dict:
    """
    The prototype score is a rough triage signal. Every case remains subject
    to human review and official scheme-specific verification.
    """
    audit_trail = []

    # 1. QR Score (Weight: 30%)
    w_qr = 0.30
    if qr_result.get("is_digitally_signed", False):
        s_qr = 100.0
        audit_trail.append("ℹ QR verifier reported a signature; confirm it using the issuing authority's trusted public key.")
    elif qr_result.get("qr_present", False):
        s_qr = 50.0
        audit_trail.append("ℹ QR payload was detected; its issuer signature has not been verified.")
    else:
        # Non-digital/handwritten document
        s_qr = 70.0
        audit_trail.append("ℹ No QR payload was detected. This alone does not indicate fraud.")

    # 2. ELA Tampering Score (Weight: 25%)
    # Invert tamper_score: 0% tampering = 100% integrity
    w_ela = 0.25
    tamper_val = ela_result.get("tamper_score", 0.0)
    s_ela = max(100.0 - tamper_val, 0.0)
    
    if ela_result.get("is_tampered", False):
        audit_trail.append(f"⚠ Image-compression anomaly signal detected (indicator: {s_ela:.1f}/100); manual inspection is required.")
    else:
        audit_trail.append(f"ℹ No strong image-compression anomaly signal detected (indicator: {s_ela:.1f}/100); authenticity is not established.")

    # 3. Identity Consistency Score (Weight: 20%)
    w_identity = 0.20
    s_identity = float(identity_result.get("average_score", 0.0))
    if identity_result.get("is_match", False):
        audit_trail.append(f"ℹ Name-string similarity signal: {s_identity:.1f}/100. No UIDAI or government identity lookup was performed.")
    else:
        audit_trail.append(f"⚠ Name-string similarity signal is low ({s_identity:.1f}/100); compare documents manually.")

    # 4. MoTA ST Gazette Score (Weight: 15%)
    w_gazette = 0.15
    if gazette_result.get("is_recognized_st", False):
        s_gazette = 100.0
        matched = gazette_result.get("matched_tribe", "Tribal")
        audit_trail.append(f"ℹ Tribe name matched the local Article 342 reference list ({matched}); certificate issuer was not authenticated.")
    else:
        s_gazette = 0.0
        audit_trail.append("⚠ No match in the local tribe reference list; confirm state, spelling, and the official schedule manually.")

    # 5. DBT Bank Readiness Score (Weight: 10%)
    w_dbt = 0.10
    if dbt_result.get("is_dbt_ready", False):
        s_dbt = 100.0
        audit_trail.append("ℹ Bank-link result is simulated locally; no NPCI or bank service was queried.")
    else:
        s_dbt = 20.0
        audit_trail.append("ℹ Simulated bank-link check returned no match; no NPCI or bank service was queried.")

    # Calculate Weighted Composite Score
    composite_score = (
        (s_qr * w_qr) +
        (s_ela * w_ela) +
        (s_identity * w_identity) +
        (s_gazette * w_gazette) +
        (s_dbt * w_dbt)
    )
    final_score = round(min(max(composite_score, 0.0), 100.0), 1)

    # Signal bands are only for prioritizing manual review.
    if final_score >= 85.0 and not ela_result.get("is_tampered", False) and gazette_result.get("is_recognized_st", False):
        decision = "GREEN"
        decision_label = "LOWER_REVIEW_SIGNAL"
        badge_color = "#10B981"
        summary = "Automated indicators are lower risk. This is not an eligibility decision; an officer must review the application."
    elif final_score >= 60.0 or not qr_result.get("qr_present", True):
        decision = "YELLOW"
        decision_label = "REVIEW_REQUIRED"
        badge_color = "#F59E0B"
        summary = "Automated indicators need review. An officer must check the documents and scheme rules."
    else:
        decision = "RED"
        decision_label = "HIGH_REVIEW_PRIORITY"
        badge_color = "#EF4444"
        summary = "Potential inconsistencies need priority manual review. Do not reject based on this signal alone."

    return {
        "final_trust_score": final_score,
        "decision": decision,
        "decision_label": decision_label,
        "badge_color": badge_color,
        "summary": summary,
        "sub_scores": {
            "qr_cryptography": s_qr,
            "ela_tampering_integrity": s_ela,
            "identity_consistency": s_identity,
            "mota_gazette_compliance": s_gazette,
            "dbt_bank_readiness": s_dbt
        },
        "audit_trail": audit_trail
    }
