"""
National Merit & Slot Allocation Engine
Module: ai_engine/merit_allocator.py

Implements transparent, multi-criteria slot allocation for competitive MoTA schemes:
- NOS (National Overseas Scholarship): Strict 20 annual slots (30% women quota, PVTG priority)
- NFST (National Fellowship for Higher Education of ST Students): 750 annual slots

Algorithm:
Composite Merit Score = (0.50 * Academic_Score) + (0.25 * Vulnerability_Score) + (0.15 * Research_Relevance) + (0.10 * Gender_Empowerment)
"""

from typing import List, Dict, Any


# Particularly Vulnerable Tribal Groups (PVTGs) recognized by MoTA
PVTG_COMMUNITIES = {
    "birhor", "asur", "korwa", "paharia", "mal paharia", "sauria paharia",
    "baiga", "bharua", "sahariya", "chenchu", "kolam", "thoti", "bondo",
    "didayi", "dongria kondh", "juang", "khadia", "kutia kondh", "lゲージa saura",
    "lodha", "mankidia", "paudi bhuyan", "saura", "cholanayakan", "kadar",
    "kattunayakan", "kurumba", "koraga", "toda", "kota", "jarawa", "onge",
    "sentinelese", "shompen", "great andamanese"
}


class MeritSlotAllocator:
    """
    Allocates competitive fellowship slots based on multi-factor normalized scoring.
    """

    def __init__(self):
        self.pvtg_set = PVTG_COMMUNITIES

    def compute_composite_merit_score(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates normalized composite merit score (0 to 100) for a candidate.

        Candidate attributes:
          - academic_percentage (float): Qualifying exam marks (0-100)
          - annual_income (float): Total family income in INR
          - caste_name (str): Specific tribe name
          - gender (str): 'FEMALE', 'MALE', 'OTHER'
          - research_experience_months (int): Published papers / experience
          - disability (bool): Persons with Disabilities (PwD)
        """
        # 1. Academic Merit Component (Weight: 50%)
        # Scaled directly from academic percentage
        raw_marks = float(candidate.get("academic_percentage", 50.0))
        academic_score = max(0.0, min(100.0, raw_marks))

        # 2. Socio-Economic Vulnerability Component (Weight: 25%)
        # Lower family income receives higher vulnerability support points
        income = float(candidate.get("annual_income", 250000.0))
        if income <= 150000.0:
            income_points = 100.0
        elif income <= 300000.0:
            income_points = 80.0
        elif income <= 600000.0:
            income_points = 55.0
        elif income <= 800000.0:
            income_points = 30.0
        else:
            income_points = 10.0

        # PVTG tribal vulnerability bonus
        caste_clean = str(candidate.get("caste_name", "")).lower().strip()
        is_pvtg = any(pvtg in caste_clean for pvtg in self.pvtg_set)
        pvtg_bonus = 20.0 if is_pvtg else 0.0

        # PwD (Divyangjan) statutory bonus
        pwd_bonus = 15.0 if candidate.get("disability", False) else 0.0

        vulnerability_score = min(100.0, income_points + pvtg_bonus + pwd_bonus)

        # 3. Research & Institutional Relevance (Weight: 15%)
        exp_months = int(candidate.get("research_experience_months", 0))
        relevance_score = min(100.0, exp_months * 4.0 + 40.0)

        # 4. Gender Empowerment & Affirmative Action (Weight: 10%)
        # Statutory 30% slot reservation policy for ST women scholars
        gender = str(candidate.get("gender", "")).upper().strip()
        if gender in ("FEMALE", "F"):
            gender_score = 100.0
        elif gender in ("OTHER", "TRANSGENDER"):
            gender_score = 100.0
        else:
            gender_score = 50.0

        # Weighted Sum Model
        composite = (
            (academic_score * 0.50) +
            (vulnerability_score * 0.25) +
            (relevance_score * 0.15) +
            (gender_score * 0.10)
        )
        final_merit_score = round(composite, 2)

        return {
            "final_merit_score": final_merit_score,
            "is_pvtg": is_pvtg,
            "breakdown": {
                "academic_score": round(academic_score, 1),
                "vulnerability_score": round(vulnerability_score, 1),
                "relevance_score": round(relevance_score, 1),
                "gender_score": round(gender_score, 1)
            }
        }

    def allocate_slots(self, candidates: List[Dict[str, Any]], total_slots: int = 20, min_women_quota_pct: float = 30.0) -> Dict[str, Any]:
        """
        Executes quota-constrained Knapsack/Greedy allocation:
        - Computes composite merit score for all verified candidates
        - Enforces statutory 30% allocation for ST female candidates
        - Fills remaining general ST merit slots strictly by score
        - Generates Waitlist queue
        """
        # Step 1: Score all candidates
        scored_candidates = []
        for c in candidates:
            score_meta = self.compute_composite_merit_score(c)
            cand_copy = dict(c)
            cand_copy["merit_score"] = score_meta["final_merit_score"]
            cand_copy["is_pvtg"] = score_meta["is_pvtg"]
            cand_copy["score_breakdown"] = score_meta["breakdown"]
            scored_candidates.append(cand_copy)

        # Step 2: Sort all descending by merit score
        scored_candidates.sort(key=lambda x: x["merit_score"], reverse=True)

        selected: List[Dict[str, Any]] = []
        waitlist: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        target_women_slots = int(total_slots * (min_women_quota_pct / 100.0))
        women_selected = 0

        # Step 3: First Pass - Reserve statutory women quota
        remaining_pool = []
        for cand in scored_candidates:
            is_woman = str(cand.get("gender", "")).upper() in ("FEMALE", "F")
            if is_woman and women_selected < target_women_slots:
                cand["allocation_category"] = "WOMEN_RESERVED"
                cand["rank"] = len(selected) + 1
                selected.append(cand)
                women_selected += 1
            else:
                remaining_pool.append(cand)

        # Step 4: Second Pass - Fill open merit slots from remaining pool
        remaining_slots = total_slots - len(selected)
        for cand in remaining_pool:
            if len(selected) < total_slots:
                cand["allocation_category"] = "OPEN_ST_MERIT"
                cand["rank"] = len(selected) + 1
                selected.append(cand)
            elif len(waitlist) < total_slots:
                cand["allocation_category"] = "WAITLISTED"
                cand["waitlist_rank"] = len(waitlist) + 1
                waitlist.append(cand)
            else:
                cand["allocation_category"] = "UNSELECTED"
                rejected.append(cand)

        # Calculate Statistics
        avg_score = round(sum(s["merit_score"] for s in selected) / max(len(selected), 1), 2)
        pvtg_count = sum(1 for s in selected if s.get("is_pvtg", False))

        return {
            "total_applicants": len(candidates),
            "allocated_slots": len(selected),
            "total_capacity": total_slots,
            "women_quota_met": women_selected >= target_women_slots,
            "women_selected_count": women_selected,
            "pvtg_selected_count": pvtg_count,
            "average_merit_score": avg_score,
            "selected_list": selected,
            "waitlist": waitlist,
            "cutoff_score": selected[-1]["merit_score"] if selected else 0.0
        }


# Singleton instance
merit_allocator = MeritSlotAllocator()


if __name__ == "__main__":
    print("--- Running Self-Test for National Merit Slot Allocator ---")

    # Sample test batch of 8 ST candidates competing for 3 NOS Overseas Slots
    sample_pool = [
        {"id": "ST-01", "name": "Birsa Munda", "academic_percentage": 78.5, "annual_income": 120000, "gender": "MALE", "caste_name": "Munda", "research_experience_months": 12},
        {"id": "ST-02", "name": "Sunita Asur", "academic_percentage": 74.0, "annual_income": 95000, "gender": "FEMALE", "caste_name": "Asur (PVTG)", "research_experience_months": 8},
        {"id": "ST-03", "name": "Pooja Oraon", "academic_percentage": 82.0, "annual_income": 350000, "gender": "FEMALE", "caste_name": "Oraon", "research_experience_months": 14},
        {"id": "ST-04", "name": "Karan Santhal", "academic_percentage": 88.0, "annual_income": 550000, "gender": "MALE", "caste_name": "Santhal", "research_experience_months": 24},
        {"id": "ST-05", "name": "Meera Baiga", "academic_percentage": 68.0, "annual_income": 80000, "gender": "FEMALE", "caste_name": "Baiga (PVTG)", "research_experience_months": 6},
        {"id": "ST-06", "name": "Rohan Ho", "academic_percentage": 62.0, "annual_income": 200000, "gender": "MALE", "caste_name": "Ho", "research_experience_months": 0},
    ]

    result = merit_allocator.allocate_slots(sample_pool, total_slots=3, min_women_quota_pct=30.0)

    print(f"\nTotal Candidates: {result['total_applicants']} | Allocated Slots: {result['allocated_slots']}")
    print(f"Cutoff Score: {result['cutoff_score']} | Avg Merit Score: {result['average_merit_score']}")
    print(f"PVTG Beneficiaries: {result['pvtg_selected_count']} | Women Selected: {result['women_selected_count']}")
    print("\nSelected Scholars (Final Allocation):")
    for s in result["selected_list"]:
        print(f"  Rank #{s['rank']} | {s['name']} ({s['gender']}) - Score: {s['merit_score']} [{s['allocation_category']}]")

    print("\nWaitlisted Scholars:")
    for w in result["waitlist"]:
        print(f"  WL #{w['waitlist_rank']} | {w['name']} - Score: {w['merit_score']}")
