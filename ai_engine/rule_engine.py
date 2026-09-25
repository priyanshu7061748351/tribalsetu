"""
TribalSetu - Dynamic Scheme Eligibility Rule Engine (SIH 2026 #26239)
Ministry of Tribal Affairs (MoTA), Government of India.

Evaluates applicant profiles against dynamic, scheme-specific statutory rules:
- Annual income caps (e.g., <= ₹2.5L for PMS-ST, <= ₹8.0L for NOS)
- Academic performance / minimum percentage requirements
- Age ceilings (e.g., <= 35 years for research fellowships)
- Article 342 Scheduled Tribe (ST) mandatory validation
- Domicile state verification
"""

import re
from typing import Dict, Any, List, Optional, Union
from ai_engine.st_gazette import st_validator


class SchemeRuleEngine:
    """
    Dynamic Scheme Rule Engine that evaluates an applicant's profile
    against statutory scheme rules without hardcoding parameters.
    """

    def __init__(self, custom_rules: Optional[Dict[str, Dict[str, Any]]] = None):
        """
        Initialize the rule engine with default MoTA scheme statutory parameters,
        with support for runtime configuration updates by Ministry Admins.
        """
        # Default MoTA Statutory Rules Database
        self.scheme_rules: Dict[str, Dict[str, Any]] = {
            "PMS-ST": {
                "name": "Post-Matric Scholarship for ST Students (PMS-ST)",
                "max_annual_income": 250000.0,
                "min_marks_percent": 50.0,
                "max_age": None,
                "st_mandatory": True,
                "domicile_scope": "ALL",
                "allowed_courses": ["Intermediate", "Diploma", "Polytechnic", "UG", "PG"]
            },
            "PRE-MATRIC-ST": {
                "name": "Pre-Matric Scholarship for ST Students (Class IX & X)",
                "max_annual_income": 250000.0,
                "min_marks_percent": 45.0,
                "max_age": 18,
                "st_mandatory": True,
                "domicile_scope": "ALL",
                "allowed_courses": ["Class IX", "Class X"]
            },
            "NFST": {
                "name": "National Fellowship for Higher Education of ST Students (NFST)",
                "max_annual_income": 600000.0,
                "min_marks_percent": 55.0,
                "max_age": 35,
                "st_mandatory": True,
                "domicile_scope": "ALL",
                "allowed_courses": ["Ph.D.", "M.Phil.", "Integrated Ph.D."]
            },
            "NOS": {
                "name": "National Overseas Scholarship for ST Candidates (NOS-ST)",
                "max_annual_income": 800000.0,
                "min_marks_percent": 60.0,
                "max_age": 35,
                "st_mandatory": True,
                "domicile_scope": "ALL",
                "allowed_courses": ["Masters Abroad", "Ph.D. Abroad"]
            },
            "NESTS": {
                "name": "National Education Society for Tribal Students (EMRS Stipend)",
                "max_annual_income": 300000.0,
                "min_marks_percent": 50.0,
                "max_age": 25,
                "st_mandatory": True,
                "domicile_scope": "ALL",
                "allowed_courses": ["UG First Year", "EMRS Alumnus"]
            }
        }

        # Allow user-provided custom overrides
        if custom_rules:
            for code, rules in custom_rules.items():
                norm_code = self._normalize_scheme_code(code)
                if norm_code in self.scheme_rules:
                    self.scheme_rules[norm_code].update(rules)
                else:
                    self.scheme_rules[norm_code] = rules

    def _normalize_scheme_code(self, scheme_code: str) -> str:
        """Normalizes scheme codes (e.g. 'pms_st' -> 'PMS-ST')."""
        if not scheme_code:
            return "PMS-ST"
        code = str(scheme_code).strip().upper().replace("_", "-")
        alias_map = {
            "PMS": "PMS-ST",
            "PMSST": "PMS-ST",
            "PRE-MATRIC": "PRE-MATRIC-ST",
            "NOS-ST": "NOS",
            "NFST-PHD": "NFST"
        }
        return alias_map.get(code, code)

    def _parse_numeric(self, value: Any, default: float = 0.0) -> float:
        """Safely parses float/int from varying string formats like '₹2,50,000' or '68.5%'."""
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        try:
            # Strip currency symbols, commas, percent, whitespace
            cleaned = re.sub(r"[^\d.]", "", str(value))
            return float(cleaned) if cleaned else default
        except (ValueError, TypeError):
            return default

    def _is_st_verified(self, applicant_data: Dict[str, Any]) -> Optional[bool]:
        """Returns True/False for explicit data, or None when evidence is missing."""
        # 1. Explicit boolean flag check
        for key in ["is_st", "is_st_verified", "st_verified", "is_scheduled_tribe"]:
            if key in applicant_data and isinstance(applicant_data[key], bool):
                return applicant_data[key]

        # 2. Category string check
        category = str(applicant_data.get("category", applicant_data.get("caste_category", ""))).strip().upper()
        if category in ["ST", "SCHEDULED TRIBE", "SCHEDULED TRIBES"]:
            return True
        if category in ["GENERAL", "GEN", "OBC", "SC", "EWS"]:
            return False

        # 3. Caste / Tribe name inspection
        tribe = str(applicant_data.get("tribe", applicant_data.get("caste", applicant_data.get("caste_name", "")))).strip()
        if not tribe:
            return None
        non_st_communities = ["rajput", "brahmin", "bhumihar", "kushwaha", "yadav"]
        if tribe.lower() in non_st_communities:
            return False
        state = applicant_data.get("domicile_state", applicant_data.get("state", ""))
        gazette_result = st_validator.validate_tribe(tribe, state=state or "jharkhand")
        return True if gazette_result.get("is_recognized_st") else None

    def update_rule(self, scheme_code: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Allows Ministry Admins to dynamically update rule parameters at runtime."""
        code = self._normalize_scheme_code(scheme_code)
        if code not in self.scheme_rules:
            return {"success": False, "error": f"Unknown scheme code: {scheme_code}"}
        self.scheme_rules[code].update(updates)
        return {"success": True, "scheme": self.scheme_rules[code]}

    def evaluate_eligibility(self, applicant_data: Dict[str, Any], scheme_code: str) -> Dict[str, Any]:
        """
        Evaluates an applicant's profile against scheme-specific statutory rules.

        Parameters:
            applicant_data (dict): Profile containing income, marks, age, caste, domicile, etc.
            scheme_code (str): Code identifying the scheme (e.g. 'PMS-ST', 'NFST', 'NOS').

        Returns:
            dict containing:
                - is_eligible (bool): True if all mandatory rules pass
                - passed_rules (list of str): Rules passed with checkmarks
                - failed_rules (list of str): Failed rules with exact deficiency reasons
                - eligibility_score (float): Percentage (0-100%) of criteria met
        """
        code = self._normalize_scheme_code(scheme_code)
        rule = self.scheme_rules.get(code)

        if not rule:
            return {
                "is_eligible": False,
                "passed_rules": [],
                "failed_rules": [f"✗ Scheme Configuration: Scheme code '{scheme_code}' is not registered under MoTA directory"],
                "eligibility_score": 0.0,
                # Backward-compatibility fields
                "eligible": False,
                "scheme_code": scheme_code,
                "rule_name": "Unregistered Scheme",
                "checks": {},
                "reasons": [f"Scheme '{scheme_code}' not found"]
            }

        passed_rules: List[str] = []
        failed_rules: List[str] = []
        pending_rules: List[str] = []
        checks: Dict[str, Optional[bool]] = {}

        # 1. ANNUAL INCOME CHECK
        max_income = rule.get("max_annual_income", 250000.0)
        income_raw = applicant_data.get("annual_income", applicant_data.get("income", applicant_data.get("family_income", None)))
        income = self._parse_numeric(income_raw, default=0.0) if income_raw is not None else None

        if income is not None:
            if income <= max_income:
                passed_rules.append(f"✓ Annual Income: ₹{income:,.0f} satisfies ceiling of ₹{max_income:,.0f}")
                checks["income_check"] = True
            else:
                failed_rules.append(f"✗ Annual Income: ₹{income:,.0f} exceeds statutory ceiling of ₹{max_income:,.0f}")
                checks["income_check"] = False
        else:
            pending_rules.append("? Annual Income: Family income certificate is required before this criterion can be assessed")
            checks["income_check"] = None

        # 2. MINIMUM MARKS PERCENTAGE CHECK
        min_marks = rule.get("min_marks_percent", 50.0)
        marks_raw = applicant_data.get("marks_percent", applicant_data.get("marks", applicant_data.get("percentage", None)))
        marks = self._parse_numeric(marks_raw, default=0.0) if marks_raw is not None else None

        if marks is not None:
            if marks >= min_marks:
                passed_rules.append(f"✓ Academic Score: {marks:.1f}% satisfies minimum threshold of {min_marks:.1f}%")
                checks["marks_check"] = True
            else:
                failed_rules.append(f"✗ Academic Score: {marks:.1f}% is below mandatory threshold of {min_marks:.1f}%")
                checks["marks_check"] = False
        else:
            pending_rules.append("? Academic Score: Marksheet is required before this criterion can be assessed")
            checks["marks_check"] = None

        # 3. AGE LIMIT CHECK (e.g. <= 35 for NFST / NOS)
        max_age = rule.get("max_age")
        if max_age is not None:
            age_raw = applicant_data.get("age", applicant_data.get("applicant_age", None))
            if age_raw is not None:
                age = int(self._parse_numeric(age_raw, default=0.0))
                if age <= max_age:
                    passed_rules.append(f"✓ Age Criterion: {age} years is within the maximum limit of {max_age} years")
                    checks["age_check"] = True
                else:
                    failed_rules.append(f"✗ Age Limit Exceeded: {age} years exceeds permissible age cap of {max_age} years")
                    checks["age_check"] = False
            else:
                pending_rules.append("? Age Criterion: Date of birth evidence is required before this criterion can be assessed")
                checks["age_check"] = None

        # 4. CONSTITUTIONAL SCHEDULED TRIBE (ST) MANDATORY CHECK
        if rule.get("st_mandatory", True):
            is_st = self._is_st_verified(applicant_data)
            tribe_name = applicant_data.get("tribe", applicant_data.get("caste", "ST Community"))
            if is_st is True:
                passed_rules.append(f"✓ Constitutional Status: Recognized Scheduled Tribe under Article 342 ({tribe_name})")
                checks["st_gazette_check"] = True
            elif is_st is False:
                category = applicant_data.get("category", applicant_data.get("caste", "Non-ST"))
                failed_rules.append(f"✗ Category Ineligible: Beneficiary category '{category}' is NOT recognized as Scheduled Tribe under MoTA Article 342 Gazette")
                checks["st_gazette_check"] = False
            else:
                pending_rules.append("? Scheduled Tribe Status: Certificate and state-specific community record require manual verification")
                checks["st_gazette_check"] = None

        # 5. DOMICILE STATE MATCH CHECK
        domicile_scope = rule.get("domicile_scope", "ALL")
        applicant_state = str(applicant_data.get("domicile_state", applicant_data.get("state", applicant_data.get("domicile", "All India")))).strip()

        if domicile_scope == "ALL" or not domicile_scope:
            passed_rules.append(f"✓ Domicile Verification: State '{applicant_state}' eligible under All-India National quota")
            checks["domicile_check"] = True
        else:
            allowed_states = [s.strip().upper() for s in (domicile_scope if isinstance(domicile_scope, list) else [domicile_scope])]
            if applicant_state.upper() in allowed_states:
                passed_rules.append(f"✓ Domicile Verification: State '{applicant_state}' matches participating scheme state list")
                checks["domicile_check"] = True
            else:
                failed_rules.append(f"✗ Domicile Mismatch: Scheme is restricted to states {allowed_states}; applicant state is '{applicant_state}'")
                checks["domicile_check"] = False

        # Compute aggregate eligibility
        total_criteria = len(passed_rules) + len(failed_rules) + len(pending_rules)
        eligibility_score = round((len(passed_rules) / total_criteria) * 100.0, 1) if total_criteria > 0 else 0.0
        is_eligible = None if pending_rules and not failed_rules else not failed_rules
        screening_status = (
            "RULES_NOT_MET_PENDING_OFFICER_REVIEW" if failed_rules else
            "PENDING_VERIFICATION" if pending_rules else
            "PRELIMINARILY_ELIGIBLE_PENDING_OFFICER_REVIEW"
        )

        return {
            "is_eligible": is_eligible,
            "passed_rules": passed_rules,
            "failed_rules": failed_rules,
            "pending_rules": pending_rules,
            "eligibility_score": eligibility_score,
            "screening_status": screening_status,
            "final_decision_requires_officer_review": True,
            # Backward-compatibility fields for server.py and test_pipeline.py
            "eligible": is_eligible,
            "scheme_code": code,
            "rule_name": rule["name"],
            "checks": checks,
            "reasons": failed_rules + pending_rules if (failed_rules or pending_rules) else ["Preliminary rules passed; officer verification is still required."]
        }

    def evaluate_applicant(self, scheme_code: str, applicant_profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Alias for evaluate_eligibility ensuring backward compatibility with
        server.py and test_pipeline.py.
        """
        return self.evaluate_eligibility(applicant_profile, scheme_code)


# Singleton instance for system-wide import
rule_engine = SchemeRuleEngine()


# =====================================================================
# SELF-TEST SUITE
# =====================================================================
if __name__ == "__main__":
    engine = SchemeRuleEngine()
    print("=" * 70)
    print("TRIBALSETU SCHEME RULE ENGINE - DYNAMIC ELIGIBILITY SELF-TEST")
    print("=" * 70)

    # -----------------------------------------------------------------
    # Test Case 1: Eligible PMS-ST student
    # (Income ₹1,20,000, ST Munda, 68% marks) -> Should be Eligible
    # -----------------------------------------------------------------
    student_1 = {
        "applicant_name": "Rahul Munda",
        "annual_income": 120000,
        "is_st": True,
        "tribe": "Munda",
        "marks_percent": 68.0,
        "state": "Jharkhand"
    }
    res_1 = engine.evaluate_eligibility(student_1, "PMS-ST")
    print("\n--- TEST CASE 1: Eligible PMS-ST Student ---")
    print(f"Candidate: {student_1['applicant_name']} (Tribe: {student_1['tribe']})")
    print(f"Is Eligible: {res_1['is_eligible']} | Score: {res_1['eligibility_score']}%")
    print("Passed Rules:")
    for r in res_1["passed_rules"]:
        print(f"  {r}")
    print("Failed Rules:")
    for r in res_1["failed_rules"]:
        print(f"  {r}")
    assert res_1["is_eligible"] is True, "Test Case 1 Failed: Student should be eligible"
    assert len(res_1["failed_rules"]) == 0, "Test Case 1 Failed: Should have 0 failed rules"
    print(">>> TEST CASE 1 PASSED! ✓")

    # -----------------------------------------------------------------
    # Test Case 2: Ineligible student exceeding income
    # (Income ₹4,50,000 for PMS-ST) -> Should be Ineligible
    # -----------------------------------------------------------------
    student_2 = {
        "applicant_name": "Sita Munda",
        "annual_income": 450000,
        "is_st": True,
        "tribe": "Munda",
        "marks_percent": 75.0,
        "state": "Jharkhand"
    }
    res_2 = engine.evaluate_eligibility(student_2, "PMS-ST")
    print("\n--- TEST CASE 2: Student Exceeding Income Ceiling ---")
    print(f"Candidate: {student_2['applicant_name']} (Income: ₹{student_2['annual_income']:,})")
    print(f"Is Eligible: {res_2['is_eligible']} | Score: {res_2['eligibility_score']}%")
    print("Passed Rules:")
    for r in res_2["passed_rules"]:
        print(f"  {r}")
    print("Failed Rules:")
    for r in res_2["failed_rules"]:
        print(f"  {r}")
    assert res_2["is_eligible"] is False, "Test Case 2 Failed: Student should be ineligible due to income"
    assert any("exceeds" in r.lower() for r in res_2["failed_rules"]), "Test Case 2 Failed: Missing income failure reason"
    print(">>> TEST CASE 2 PASSED! ✓")

    # -----------------------------------------------------------------
    # Test Case 3: Ineligible non-ST applicant
    # (Category General / Rajput) -> Should be Ineligible
    # -----------------------------------------------------------------
    student_3 = {
        "applicant_name": "Vikas Singh",
        "annual_income": 150000,
        "is_st": False,
        "category": "General",
        "caste": "Rajput",
        "marks_percent": 82.0,
        "state": "Jharkhand"
    }
    res_3 = engine.evaluate_eligibility(student_3, "PMS-ST")
    print("\n--- TEST CASE 3: Ineligible Non-ST Applicant ---")
    print(f"Candidate: {student_3['applicant_name']} (Category: {student_3['category']})")
    print(f"Is Eligible: {res_3['is_eligible']} | Score: {res_3['eligibility_score']}%")
    print("Passed Rules:")
    for r in res_3["passed_rules"]:
        print(f"  {r}")
    print("Failed Rules:")
    for r in res_3["failed_rules"]:
        print(f"  {r}")
    assert res_3["is_eligible"] is False, "Test Case 3 Failed: Non-ST applicant should be ineligible"
    assert any("scheduled tribe" in r.lower() or "category" in r.lower() for r in res_3["failed_rules"]), "Test Case 3 Failed: Missing ST status failure reason"
    print(">>> TEST CASE 3 PASSED! ✓")

    print("\n" + "=" * 70)
    print("ALL 3 RULE ENGINE TEST CASES COMPLETED SUCCESSFULLY!")
    print("=" * 70)
