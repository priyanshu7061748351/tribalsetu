"""
TribalSetu - Research Supervisor & NFST Fellowship Portal
Automates post-selection fellowship lifecycle for 750 NFST Ph.D. scholars:
- Bi-annual progress report verification
- University registration renewal tracking
- Milestone-based monthly stipend (₹31,000 - ₹35,000) disbursement authorization
"""

import time
from typing import Dict, List, Any

class FellowshipManager:
    def __init__(self):
        # In-memory fellows directory
        self.fellows_db = [
            {
                "fellow_id": "NFST-2026-PHD-042",
                "scholar_name": "Sunita Kumari Oraon",
                "tribe": "Oraon",
                "state": "Jharkhand",
                "university": "Ranchi University",
                "department": "Tribal & Regional Languages",
                "supervisor_name": "Prof. Ramchandra Soren",
                "phd_topic": "Ethnobotanical Traditions of Chota Nagpur Plateau",
                "current_stipend_monthly": 31000.0,
                "contingency_annual": 10000.0,
                "current_semester": 4,
                "last_review_date": "15-Aug-2026",
                "supervisor_signed": True,
                "milestone_status": "MILESTONE_SATISFACTORY",
                "stipend_disbursement": "RELEASED_PFMS"
            },
            {
                "fellow_id": "NFST-2026-PHD-089",
                "scholar_name": "Mangal Munda",
                "tribe": "Munda",
                "state": "Jharkhand",
                "university": "Birsa Agricultural University",
                "department": "Agronomy & Indigenous Grains",
                "supervisor_name": "Dr. Anjali Kerketta",
                "phd_topic": "Drought-Resilient Traditional Millet Varieties of Santhal Pargana",
                "current_stipend_monthly": 35000.0,
                "contingency_annual": 10000.0,
                "current_semester": 6,
                "last_review_date": "01-Sep-2026",
                "supervisor_signed": False,
                "milestone_status": "PENDING_SUPERVISOR_SIGNATURE",
                "stipend_disbursement": "AWAITING_APPROVAL"
            }
        ]

    def get_all_fellows(self) -> List[Dict[str, Any]]:
        return self.fellows_db

    def supervisor_endorse_milestone(self, fellow_id: str, supervisor_id: str, remarks: str, grant_extension: bool = False) -> Dict[str, Any]:
        """Supervisor digitally signs the bi-annual progress review to release monthly stipend"""
        for f in self.fellows_db:
            if f["fellow_id"] == fellow_id:
                f["supervisor_signed"] = True
                f["milestone_status"] = "MILESTONE_SATISFACTORY"
                f["stipend_disbursement"] = "APPROVED_READY_FOR_PFMS"
                f["last_review_date"] = "Today"
                f["supervisor_notes"] = remarks
                return {
                    "success": True,
                    "message": f"Fellowship milestone for {f['scholar_name']} successfully endorsed. Monthly stipend of ₹{f['current_stipend_monthly']:,.0f} queued for PFMS DBT transfer.",
                    "record": f
                }
        return {"success": False, "error": "Fellow record not found."}

fellowship_manager = FellowshipManager()
