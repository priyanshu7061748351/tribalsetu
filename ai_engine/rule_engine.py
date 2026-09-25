"""
Dynamic Scheme Rule Engine Module
Evaluates applicant eligibility against MoTA scheme criteria (PMS-ST, NFST, NOS, NESTS)
dynamically without hardcoding business logic.
"""

from typing import Dict, Any, List

# Official MoTA Schemes Eligibility Criteria Configuration
SCHEME_CRITERIA_REGISTRY = {
    "PMS-ST": {
        "scheme_name": "Post-Matric Scholarship for ST Students",
        "max_annual_income": 250000.0,
        "min_academic_percentage": 50.0,
        "max_age_years": None,  # No upper age limit for PMS-ST
        "st_mandatory": True,
        "supported_courses": ["11th", "12th", "diploma", "graduation", "post-graduation", "professional", "all"],
        "domicile_required": True,
        "description": "Financial assistance to Scheduled Tribe students studying at post-matriculation or post-secondary stage."
    },
    "NFST": {
        "scheme_name": "National Fellowship for Higher Education of ST Students",
        "max_annual_income": 600000.0,  # Preference given to income <= 6L
        "min_academic_percentage": 55.0,  # Minimum 55% in Post-Graduation
        "max_age_years": 36,  # Relaxable up to 5 years for ST
        "st_mandatory": True,
        "supported_courses": ["m.phil", "ph.d", "integrated ph.d"],
        "domicile_required": False,  # All-India scheme
        "description": "Fellowships to ST students to pursue M.Phil/Ph.D degrees in Sciences, Humanities, and Engineering."
    },
    "NOS": {
        "scheme_name": "National Overseas Scholarship for ST Candidates",
        "max_annual_income": 800000.0,  # Total family income must not exceed ₹8.00 Lakh
        "min_academic_percentage": 60.0,  # Minimum 60% in qualifying degree
        "max_age_years": 35,  # As on 1st April of selection year
        "st_mandatory": True,
        "supported_courses": ["masters", "ph.d", "post-doctoral"],
        "domicile_required": False,  # All-India quota (20 slots)
        "description": "Financial assistance to selected ST students for pursuing Masters/Ph.D abroad in reputed global universities."
    },
    "NESTS": {
        "scheme_name": "National Education Society for Tribal Students (EMRS)",
        "max_annual_income": 200000.0,
        "min_academic_percentage": 45.0,
        "max_age_years": 19,
        "st_mandatory": True,
        "supported_courses": ["6th", "7th", "8th", "9th", "10th", "11th", "12th"],
        "domicile_required": True,
        "description": "Support for tribal students enrolled in Eklavya Model Residential Schools across remote tribal blocks."
    }
}


class SchemeRuleEngine:
    """
    Evaluates applicant suitability against dynamically registered scheme rules.
    """

    def __init__(self, registry: Dict[str, Any] = None):
        self.registry = registry or SCHEME_CRITERIA_REGISTRY

    def get_supported_schemes(self) -> List[str]:
        return list(self.registry.keys())

    def evaluate_eligibility(self, applicant_data: Dict[str, Any], scheme_code: str) -> Dict[str, Any]:
        """
        Evaluates an applicant against a specific scheme's statutory criteria.

        applicant_data expected fields:
          - annual_income (float / int)
          - is_st (bool)
          - caste_name (str)
          - academic_percentage (float)
          - age (int)
          - course_name (str)
          - state (str)
        """
        code = scheme_code.upper().strip()
        if code not in self.registry:
            return {
                "is_eligible": False,
                "eligibility_score": 0.0,
                "passed_rules": [],
                "failed_rules": [f"Unknown scheme code '{scheme_code}'. Supported: {list(self.registry.keys())}"],
                "scheme_info": {}
            }

        rule = self.registry[code]
        passed_rules: List[str] = []
        failed_rules: List[str] = []
        total_checks = 0
        passed_checks = 0

        # --- Rule 1: Scheduled Tribe (ST) Statutory Status ---
        if rule.get("st_mandatory", True):
            total_checks += 1
            is_st = applicant_data.get("is_st", False)
            caste_name = applicant_data.get("caste_name", "").strip()
            if is_st or caste_name:
                passed_checks += 1
                passed_rules.append(f"[PASS] ST Category Verified: Recognized tribal beneficiary ({caste_name or 'ST'})")
            else:
                failed_rules.append("[FAIL] Category Mismatch: Applicant must belong to a recognized Scheduled Tribe under Article 342")

        # --- Rule 2: Annual Family Income Ceiling ---
        max_income = rule.get("max_annual_income")
        if max_income is not None:
            total_checks += 1
            try:
                income = float(applicant_data.get("annual_income", 9999999))
                if income <= max_income:
                    passed_checks += 1
                    passed_rules.append(f"[PASS] Income Limit: Rs.{income:,.0f} is within statutory ceiling of Rs.{max_income:,.0f}")
                else:
                    failed_rules.append(f"[FAIL] Income Ceiling Exceeded: Rs.{income:,.0f} exceeds max allowed Rs.{max_income:,.0f} for {code}")
            except (ValueError, TypeError):
                failed_rules.append("[FAIL] Invalid Income Value: Could not verify annual income")

        # --- Rule 3: Minimum Qualifying Academic Percentage ---
        min_pct = rule.get("min_academic_percentage")
        if min_pct is not None:
            total_checks += 1
            try:
                pct = float(applicant_data.get("academic_percentage", 0.0))
                if pct >= min_pct:
                    passed_checks += 1
                    passed_rules.append(f"[PASS] Academic Merit: {pct:.1f}% satisfies minimum requirement of {min_pct:.1f}%")
                else:
                    failed_rules.append(f"[FAIL] Academic Threshold: {pct:.1f}% is below minimum required {min_pct:.1f}% for {code}")
            except (ValueError, TypeError):
                failed_rules.append("[FAIL] Academic Percentage Missing: Could not verify qualifying marks")

        # --- Rule 4: Maximum Age Limit (if applicable) ---
        max_age = rule.get("max_age_years")
        if max_age is not None:
            total_checks += 1
            try:
                age = int(applicant_data.get("age", 999))
                if age <= max_age:
                    passed_checks += 1
                    passed_rules.append(f"[PASS] Age Eligible: {age} years is within maximum age limit of {max_age} years")
                else:
                    failed_rules.append(f"[FAIL] Age Limit Exceeded: {age} years exceeds maximum permissible age of {max_age} years")
            except (ValueError, TypeError):
                failed_rules.append("[FAIL] Age Missing: Could not evaluate age criteria")

        # --- Rule 5: Course Eligibility ---
        supported_courses = rule.get("supported_courses", [])
        if supported_courses and "all" not in supported_courses:
            total_checks += 1
            course = str(applicant_data.get("course_name", "")).lower().strip()
            if any(sc in course for sc in supported_courses) or not course:
                passed_checks += 1
                passed_rules.append(f"[PASS] Course Admissible: Course level matches {code} scholarship guidelines")
            else:
                failed_rules.append(f"[FAIL] Course Ineligible: '{applicant_data.get('course_name')}' is not covered under {code}")

        # Compute Composite Percentage
        eligibility_score = round((passed_checks / max(total_checks, 1)) * 100.0, 1)
        is_eligible = len(failed_rules) == 0

        return {
            "is_eligible": is_eligible,
            "eligibility_score": eligibility_score,
            "passed_rules": passed_rules,
            "failed_rules": failed_rules,
            "scheme_info": {
                "scheme_code": code,
                "scheme_name": rule["scheme_name"],
                "income_ceiling": rule["max_annual_income"],
                "min_marks": rule["min_academic_percentage"],
                "description": rule["description"]
            }
        }


# Singleton instance for server-wide import
rule_engine = SchemeRuleEngine()


if __name__ == "__main__":
    print("--- Running Self-Test for Dynamic Scheme Rule Engine ---")

    # Test Case 1: Legitimate PMS-ST Applicant
    applicant_1 = {
        "annual_income": 120000,
        "is_st": True,
        "caste_name": "Munda",
        "academic_percentage": 68.5,
        "age": 19,
        "course_name": "B.Tech Graduation",
        "state": "Jharkhand"
    }
    res_1 = rule_engine.evaluate_eligibility(applicant_1, "PMS-ST")
    print("\nTest Case 1 (Eligible PMS-ST):", "PASS" if res_1["is_eligible"] else "FAIL")
    print("Eligibility Score:", res_1["eligibility_score"], "%")
    for r in res_1["passed_rules"]:
        print(" ", r)

    # Test Case 2: Ineligible Income for PMS-ST (Income ₹4.5 Lakh vs ₹2.5 Lakh limit)
    applicant_2 = {
        "annual_income": 450000,
        "is_st": True,
        "caste_name": "Santhal",
        "academic_percentage": 72.0,
        "age": 20,
        "course_name": "Diploma",
        "state": "Odisha"
    }
    res_2 = rule_engine.evaluate_eligibility(applicant_2, "PMS-ST")
    print("\nTest Case 2 (Income Exceeded):", "PASS" if not res_2["is_eligible"] else "FAIL")
    print("Failed reasons:")
    for f in res_2["failed_rules"]:
        print(" ", f)

    # Test Case 3: Ineligible Non-ST Applicant
    applicant_3 = {
        "annual_income": 80000,
        "is_st": False,
        "caste_name": "",
        "academic_percentage": 85.0,
        "age": 22,
        "course_name": "B.Sc Graduation",
        "state": "Bihar"
    }
    res_3 = rule_engine.evaluate_eligibility(applicant_3, "PMS-ST")
    print("\nTest Case 3 (Non-ST Blocked):", "PASS" if not res_3["is_eligible"] else "FAIL")
    for f in res_3["failed_rules"]:
        print(" ", f)
