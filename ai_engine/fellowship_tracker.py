"""
Post-Selection Fellowship & Research Supervisor Management Module
Module: ai_engine/fellowship_tracker.py

Solves Problem Statement issue:
"post-selection/fellowship management... resulting in processing delays, repetitive administrative effort"

Specifically addresses NFST (National Fellowship for Higher Education of ST Students)
and NOS (National Overseas Scholarship) scholars:
- Bi-annual progress report verification by University Supervisor
- Automated monthly stipend release calculation (JRF: Rs.37,000/mo, SRF: Rs.42,000/mo + HRA)
- Research milestone tracking (Coursework, Synopsis, Pre-submission, Final Viva)
"""

import time
from typing import Dict, Any, List


class FellowshipLifecycleManager:
    """
    Manages ongoing research scholars, supervisor milestone sign-offs, and stipend triggers.
    """

    # Official UGC / MoTA Revised Fellowship Rates
    RATES = {
        "JRF": {"stipend_monthly": 37000.0, "contingency_annual": 10000.0, "hra_pct": 27.0},
        "SRF": {"stipend_monthly": 42000.0, "contingency_annual": 20500.0, "hra_pct": 27.0}
    }

    def __init__(self):
        # In-memory scholar registry: {scholar_id: scholar_profile}
        self.scholars: Dict[str, Dict[str, Any]] = {}

    def enroll_awarded_scholar(
        self,
        application_id: str,
        scholar_name: str,
        university_name: str,
        department: str,
        research_topic: str,
        supervisor_name: str,
        supervisor_email: str,
        scheme_code: str = "NFST",
        fellowship_level: str = "JRF"
    ) -> Dict[str, Any]:
        """
        Enrolls an approved candidate into the post-selection fellowship lifecycle.
        """
        scholar_id = f"NFST-{time.strftime('%Y')}-{len(self.scholars) + 101:03d}"
        rate_info = self.RATES.get(fellowship_level, self.RATES["JRF"])
        monthly_hra = rate_info["stipend_monthly"] * (rate_info["hra_pct"] / 100.0)
        total_monthly_payout = rate_info["stipend_monthly"] + monthly_hra

        profile = {
            "scholar_id": scholar_id,
            "application_id": application_id,
            "scholar_name": scholar_name,
            "university_name": university_name,
            "department": department,
            "research_topic": research_topic,
            "supervisor": {
                "name": supervisor_name,
                "email": supervisor_email,
                "status": "ACTIVE_REGISTERED"
            },
            "scheme_code": scheme_code,
            "fellowship_level": fellowship_level,
            "tenure_months_total": 60,  # 5 years maximum tenure
            "tenure_months_completed": 0,
            "monthly_entitlement": {
                "basic_stipend": rate_info["stipend_monthly"],
                "hra_amount": round(monthly_hra, 2),
                "total_monthly_disbursement": round(total_monthly_payout, 2)
            },
            "milestones": [
                {"title": "Coursework Completion", "status": "PENDING", "completed_date": None},
                {"title": "Ph.D Synopsis Registration", "status": "PENDING", "completed_date": None},
                {"title": "Mid-Term JRF to SRF Assessment", "status": "PENDING", "completed_date": None},
                {"title": "Pre-Thesis Submission Colloquium", "status": "PENDING", "completed_date": None},
                {"title": "Final Thesis Defense & Degree Award", "status": "PENDING", "completed_date": None}
            ],
            "progress_reports": [],
            "disbursement_history": []
        }

        self.scholars[scholar_id] = profile
        return {"success": True, "scholar_id": scholar_id, "profile": profile}

    def submit_supervisor_progress_report(
        self,
        scholar_id: str,
        report_period: str,
        attendance_percentage: float,
        research_quality_rating: str,
        supervisor_recommendation: str,
        supervisor_remarks: str = ""
    ) -> Dict[str, Any]:
        """
        Supervisor logs in and endorses bi-annual progress. Triggers automated stipend clearance.
        """
        if scholar_id not in self.scholars:
            return {"success": False, "message": f"Scholar ID '{scholar_id}' not found."}

        scholar = self.scholars[scholar_id]
        is_approved = supervisor_recommendation.upper() in ("APPROVED", "SATISFACTORY", "EXCELLENT")

        report_entry = {
            "report_id": f"REP-{int(time.time())}",
            "period": report_period,
            "submitted_at": time.strftime("%d-%b-%Y %H:%M:%S"),
            "attendance_percentage": attendance_percentage,
            "research_rating": research_quality_rating,
            "is_endorsed_by_supervisor": is_approved,
            "supervisor_remarks": supervisor_remarks or "Research progress satisfactory. Recommended for stipend release."
        }

        scholar["progress_reports"].append(report_entry)

        # Trigger automatic 6-month stipend clearance if approved
        if is_approved:
            monthly_amt = scholar["monthly_entitlement"]["total_monthly_disbursement"]
            cleared_amt = round(monthly_amt * 6, 2)
            disbursement_event = {
                "transaction_id": f"PFMS-{int(time.time())}",
                "amount": cleared_amt,
                "period": report_period,
                "status": "TRANSFERRED_VIA_PFMS_DBT",
                "date": time.strftime("%d-%b-%Y")
            }
            scholar["disbursement_history"].append(disbursement_event)
            scholar["tenure_months_completed"] += 6

            return {
                "success": True,
                "message": f"Progress report for {report_period} approved! Automated PFMS disbursement of Rs.{cleared_amt:,.2f} triggered.",
                "disbursement": disbursement_event
            }
        else:
            return {
                "success": False,
                "message": "Progress flagged as unsatisfactory by Supervisor. Stipend temporarily withheld pending inquiry.",
                "report": report_entry
            }


# Singleton instance
fellowship_manager = FellowshipLifecycleManager()


if __name__ == "__main__":
    print("--- Running Self-Test for Fellowship & Supervisor Manager ---")

    # Enroll new NFST Ph.D scholar
    res_enroll = fellowship_manager.enroll_awarded_scholar(
        application_id="APP-2026-002",
        scholar_name="Suresh Oraon",
        university_name="Ranchi University",
        department="Tribal Studies & Anthropology",
        research_topic="Ethnobotanical Traditions of Chota Nagpur Plateau ST Communities",
        supervisor_name="Dr. Arvind Minz",
        supervisor_email="arvind.minz@ranchiuniv.ac.in",
        scheme_code="NFST",
        fellowship_level="JRF"
    )

    sid = res_enroll["scholar_id"]
    prof = res_enroll["profile"]
    print(f"\nScholar Enrolled: {sid} - {prof['scholar_name']}")
    print(f"Monthly Entitlement (Basic + HRA): Rs.{prof['monthly_entitlement']['total_monthly_disbursement']:,.2f}")

    # Supervisor submits 6-month progress report
    res_report = fellowship_manager.submit_supervisor_progress_report(
        scholar_id=sid,
        report_period="Jan-2026 to Jun-2026",
        attendance_percentage=94.0,
        research_quality_rating="EXCELLENT",
        supervisor_recommendation="APPROVED",
        supervisor_remarks="Fieldwork completed in 12 villages. Two research papers submitted to UGC-CARE journal."
    )

    print("\nSupervisor Sign-Off:")
    print(res_report["message"])
