"""
TribalSetu - National Merit & Slot Allocation Engine
Implements multi-objective merit sorting & knapsack slot allocation for
competitive MoTA schemes (NFST: 750 slots, NOS: 20 slots).
Factors in normalized academic percentile, female reservation, PVTG (Particularly
Vulnerable Tribal Groups) weighting, and economic vulnerability.
"""

from typing import List, Dict, Any

class MeritSlotAllocator:
    def __init__(self):
        self.pvtg_communities = {
            "birhor", "asur", "korwa", "sauria pahariya", "mal pahariya",
            "bondo", "chenchu", "didayi", "dongria kondh", "lodha",
            "baiga", "bharwa", "sahariya", "kamar", "abujh maria", "katkari"
        }

    def compute_composite_merit_score(self, candidate: Dict[str, Any]) -> float:
        """
        Calculates normalized composite merit score (0 - 100):
        - Academic Score (Marks %): 50%
        - Economic Vulnerability (Lower income = higher points): 25%
        - PVTG Statutory Priority Weight: 15%
        - Gender Inclusion (Female ST representation): 10%
        """
        # 1. Academic Weight (0-50 pts)
        academic_score = min(float(candidate.get("marks_percent", 0.0)), 100.0) * 0.50

        # 2. Economic Vulnerability (0-25 pts)
        # Income < 1.0L gets 25 pts, scales down to 0 at 8.0L
        income = float(candidate.get("annual_income", 250000.0))
        if income <= 100000.0:
            economic_score = 25.0
        elif income <= 250000.0:
            economic_score = 20.0
        elif income <= 500000.0:
            economic_score = 12.0
        elif income <= 800000.0:
            economic_score = 5.0
        else:
            economic_score = 0.0

        # 3. PVTG Community Priority (15 pts)
        caste = str(candidate.get("caste", "")).lower().strip()
        is_pvtg = caste in self.pvtg_communities
        pvtg_score = 15.0 if is_pvtg else 0.0

        # 4. Gender Representation (10 pts for female / third gender)
        gender = str(candidate.get("gender", "")).lower().strip()
        gender_score = 10.0 if gender in ["female", "transgender", "f"] else 5.0

        total_merit = academic_score + economic_score + pvtg_score + gender_score
        return round(total_merit, 2)

    def allocate_slots(self, candidates: List[Dict[str, Any]], total_slots: int = 20, min_female_quota: float = 0.30) -> Dict[str, Any]:
        """
        Allocates slots adhering to statutory 30% female reservation & merit order.
        """
        scored_candidates = []
        for c in candidates:
            c_copy = dict(c)
            c_copy["merit_score"] = self.compute_composite_merit_score(c)
            scored_candidates.append(c_copy)

        # Sort descending by merit score
        scored_candidates.sort(key=lambda x: x["merit_score"], reverse=True)

        selected = []
        waiting_list = []
        female_target = int(total_slots * min_female_quota)
        female_count = 0

        # Pass 1: Select top candidates
        for c in scored_candidates:
            if len(selected) < total_slots:
                is_female = str(c.get("gender", "")).lower().strip() in ["female", "f"]
                selected.append(c)
                if is_female:
                    female_count += 1
            else:
                waiting_list.append(c)

        # Pass 2: Ensure minimum female representation quota if deficit exists
        if female_count < female_target:
            needed = female_target - female_count
            # Find eligible female candidates in waiting list
            female_waiters = [w for w in waiting_list if str(w.get("gender", "")).lower().strip() in ["female", "f"]]
            for f_cand in female_waiters[:needed]:
                # Swap out lowest scoring male in selected
                for i in range(len(selected) - 1, -1, -1):
                    if str(selected[i].get("gender", "")).lower().strip() not in ["female", "f"]:
                        displaced = selected.pop(i)
                        selected.append(f_cand)
                        waiting_list.remove(f_cand)
                        waiting_list.append(displaced)
                        break

        # Re-sort final selected by rank
        selected.sort(key=lambda x: x["merit_score"], reverse=True)
        for idx, s in enumerate(selected, 1):
            s["merit_rank"] = idx

        return {
            "total_applicants": len(candidates),
            "allocated_slots": len(selected),
            "available_slots": total_slots,
            "selected_beneficiaries": selected,
            "waiting_list_top5": waiting_list[:5],
            "cutoff_merit_score": selected[-1]["merit_score"] if selected else 0.0
        }

merit_allocator = MeritSlotAllocator()
