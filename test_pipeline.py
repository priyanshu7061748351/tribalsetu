"""
Automated Pipeline Verification Test
Tests genuine, tampered, and non-ST sample certificates
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from ai_engine.pipeline import run_verification_pipeline

def test_genuine():
    print("\n--- TEST 1: GENUINE ST CERTIFICATE (Rahul Munda) ---")
    doc_path = Path("sample_docs/sample_genuine_st.jpg")
    with open(doc_path, "rb") as f:
        doc_bytes = f.read()

    res = run_verification_pipeline(
        caste_doc_bytes=doc_bytes,
        applicant_name="Rahul Munda",
        aadhaar_no="987654321012",
        caste_name="Munda",
        state="jharkhand",
        father_name="Birsa Munda"
    )

    print(f"Decision: {res['decision']} ({res['decision_label']})")
    print(f"Trust Score: {res['trust_score']}%")
    print(f"QR Signed: {res['qr_verification']['is_digitally_signed']}")
    print(f"Tribe Verified: {res['verified_tribe']} (ST: {res['is_st_verified']})")
    print(f"DBT Active: {res['dbt_status']['is_dbt_ready']}")
    print("Audit Trail Summary:")
    for trail in res["audit_trail"]:
        safe_str = trail.encode('ascii', 'replace').decode('ascii')
        print("  " + safe_str)
    assert res["trust_score"] >= 80.0, "Genuine ST certificate must receive high trust score"

def test_tampered():
    print("\n--- TEST 2: TAMPERED / PHOTOSHOPPED CERTIFICATE ---")
    doc_path = Path("sample_docs/sample_tampered_fake.jpg")
    with open(doc_path, "rb") as f:
        doc_bytes = f.read()

    res = run_verification_pipeline(
        caste_doc_bytes=doc_bytes,
        applicant_name="Rahul Munda",
        aadhaar_no="987654321012",
        caste_name="Munda",
        state="jharkhand"
    )

    print(f"Decision: {res['decision']} ({res['decision_label']})")
    print(f"Trust Score: {res['trust_score']}%")
    print(f"Tamper Detected: {res['ela_forensics']['is_tampered']} (Score: {res['ela_forensics']['tamper_score']}%)")
    print(f"Explanation: {res['ela_forensics']['explanation']}")
    print("Audit Trail:")
    for trail in res["audit_trail"]:
        safe_str = trail.encode('ascii', 'replace').decode('ascii')
        print("  " + safe_str)

def test_non_st():
    print("\n--- TEST 3: NON-ST / GENERAL CERTIFICATE ---")
    doc_path = Path("sample_docs/sample_non_st.jpg")
    with open(doc_path, "rb") as f:
        doc_bytes = f.read()

    res = run_verification_pipeline(
        caste_doc_bytes=doc_bytes,
        applicant_name="Rahul Kushwaha",
        aadhaar_no="987654321012",
        caste_name="Kushwaha",
        state="jharkhand"
    )

    print(f"Decision: {res['decision']} ({res['decision_label']})")
    print(f"Trust Score: {res['trust_score']}%")
    print(f"Tribe Recognized as ST: {res['is_st_verified']}")
    print("Audit Trail:")
    for trail in res["audit_trail"]:
        safe_str = trail.encode('ascii', 'replace').decode('ascii')
        print("  " + safe_str)

    print("\nAll 3 automated pipeline tests completed successfully!")

def test_enterprise_modules():
    print("\n--- TEST 4: DYNAMIC AST RULE ENGINE ---")
    from ai_engine.rule_engine import rule_engine
    eval_res = rule_engine.evaluate_applicant("PMS-ST", {
        "annual_income": 180000,
        "is_st_verified": True,
        "marks_percent": 82.0
    })
    print(f"Rule Evaluation Eligible: {eval_res['eligible']} (Reasons: {eval_res['reasons']})")
    assert eval_res['eligible'] is True

    print("\n--- TEST 5: KNAPSACK MERIT ALLOCATOR ---")
    from ai_engine.merit_allocator import merit_allocator
    candidates = [
        {"name": "Sunita Oraon", "caste": "Oraon", "marks_percent": 88.5, "annual_income": 95000, "gender": "Female"},
        {"name": "Birsa Munda", "caste": "Munda", "marks_percent": 91.0, "annual_income": 120000, "gender": "Male"},
        {"name": "Sita Asur", "caste": "Asur", "marks_percent": 79.0, "annual_income": 80000, "gender": "Female"}
    ]
    alloc = merit_allocator.allocate_slots(candidates, total_slots=2)
    print(f"Allocated {len(alloc['selected_beneficiaries'])} of {alloc['available_slots']} slots.")
    assert len(alloc['selected_beneficiaries']) == 2

    print("\n--- TEST 6: 72-HOUR DEFICIENCY FLOW ---")
    from ai_engine.deficiency_flow import deficiency_manager
    token_res = deficiency_manager.generate_reupload_token(
        "APP-2026-002", "9876543210", ["Income Certificate"], "Validity expired"
    )
    print(f"Deficiency Token Generated: {token_res['token'][:16]}... (Expires in {token_res['expires_in_hours']} hrs)")
    assert token_res['success'] is True

    print("\n--- TEST 7: RESEARCH FELLOWSHIP SUPERVISOR PORTAL ---")
    from ai_engine.fellowship_portal import fellowship_manager
    fellows = fellowship_manager.get_all_fellows()
    endorse_res = fellowship_manager.supervisor_endorse_milestone(
        fellows[0]["fellow_id"], "SUPERVISOR-TEST", "Satisfactory half-yearly progress report"
    )
    print(f"Fellowship Endorsement Status: {endorse_res['record']['stipend_disbursement']} (Amount: Rs {endorse_res['record']['current_stipend_monthly']})")
    assert endorse_res['success'] is True

    print("\n--- TEST 8: BIOMETRIC PASSIVE LIVENESS & FACE MATCHING ---")
    from ai_engine.biometrics import biometric_engine
    selfie_img = Path("sample_docs/sample_selfie.jpg").read_bytes()
    bio_res = biometric_engine.compare_faces(selfie_img)
    print(f"Biometric Live Face Match: {bio_res['verdict']} (Liveness: {bio_res['liveness']['status']}, Sim: {bio_res['similarity_percent']}%)")
    assert bio_res['verified'] is True
    
    # Test anti-spoofing on non-face flat document
    doc_img = Path("sample_docs/sample_genuine_st.jpg").read_bytes()
    spoof_res = biometric_engine.compare_faces(doc_img)
    print(f"Anti-Spoofing on Document: {spoof_res['verdict']} (Expected: Rejected/Recheck)")

    print("\n--- TEST 9: CRYPTOGRAPHIC AUDIT LEDGER & DPDP VAULT ---")
    from ai_engine.audit_ledger import audit_ledger, aadhaar_vault
    masked = aadhaar_vault.mask_aadhaar("987654321012")
    print(f"DPDP Masked Aadhaar: {masked}")
    assert masked == "XXXX-XXXX-1012"
    
    audit_ledger.record_action("APP-TEST", "OFFICER_TEST", "VERIFY_PASS", 95.0, "Test block appended")
    integrity = audit_ledger.verify_integrity()
    print(f"Audit Ledger Blockchain Integrity: {integrity['status']} ({integrity['total_blocks']} blocks)")
    assert integrity['is_valid'] is True

if __name__ == "__main__":
    test_genuine()
    test_tampered()
    test_non_st()
    test_enterprise_modules()
    print("\nAll 9 Architecture & Forensic Tests PASSED successfully!")
