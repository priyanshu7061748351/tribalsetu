"""
Identity Cross-Matching Module
Function 6: cross_match_identity()
Compares applicant name strings using fuzzy matching. This does not authenticate
identity against UIDAI or another government record.
"""

from thefuzz import fuzz

def cross_match_identity(
    aadhaar_name: str,
    caste_doc_name: str,
    marksheet_name: str,
    aadhaar_father: str = "",
    caste_father: str = ""
) -> dict:
    """
    Computes a cross-document string-similarity signal using Levenshtein Token Sort Ratio.
    Returns:
      - is_match (bool): True if the configured string-similarity threshold is met
      - average_score (float): Composite match score (0 to 100%)
      - breakdown (dict): Detailed pairwise scores
      - explanation (str): Audit feedback
    """
    if not aadhaar_name or not caste_doc_name:
        return {
            "is_match": False,
            "average_score": 0.0,
            "breakdown": {},
            "explanation": "Missing name strings for identity verification."
        }

    # Normalize strings (lowercase, stripped)
    a_name = aadhaar_name.strip().lower()
    c_name = caste_doc_name.strip().lower()
    m_name = marksheet_name.strip().lower() if marksheet_name else c_name

    # 1. Pairwise Token Sort Ratio (Ignores word order differences, e.g., 'Munda Birsa' vs 'Birsa Munda')
    score_aadhaar_caste = fuzz.token_sort_ratio(a_name, c_name)
    score_caste_marksheet = fuzz.token_sort_ratio(c_name, m_name)
    score_aadhaar_marksheet = fuzz.token_sort_ratio(a_name, m_name)

    # 2. Father's Name Match (if available)
    father_score = 100
    if aadhaar_father and caste_father:
        father_score = fuzz.token_sort_ratio(aadhaar_father.strip().lower(), caste_father.strip().lower())

    # 3. Weighted Composite Score
    weights = [0.4, 0.3, 0.3]
    composite_name_score = (score_aadhaar_caste * weights[0]) + (score_caste_marksheet * weights[1]) + (score_aadhaar_marksheet * weights[2])

    final_identity_score = (composite_name_score * 0.8) + (father_score * 0.2)

    # Threshold: >= 82% allows genuine minor typos (e.g. Birsa vs Birsha or missing 'Kumar')
    # but strictly flags completely different names (e.g. Amit vs Rahul)
    is_match = final_identity_score >= 80.0

    if is_match:
        if final_identity_score >= 95.0:
            expl = f"High name-string similarity ({final_identity_score:.1f}%). No UIDAI or government identity record was queried."
        else:
            expl = f"Name-string similarity signal with spelling variation (score: {final_identity_score:.1f}%). No UIDAI or government identity record was queried."
    else:
        expl = f"Name-string similarity is low ({final_identity_score:.1f}%). Check the documents manually; this is not an identity verification result."

    return {
        "is_match": is_match,
        "average_score": round(final_identity_score, 1),
        "breakdown": {
            "aadhaar_vs_caste": score_aadhaar_caste,
            "caste_vs_marksheet": score_caste_marksheet,
            "aadhaar_vs_marksheet": score_aadhaar_marksheet,
            "father_name_match": father_score
        },
        "explanation": expl
    }
