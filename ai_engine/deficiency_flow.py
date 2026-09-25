"""
TribalSetu - Deficiency Notice & 72-Hour Re-Upload Workflow
Automates defect cure cycles for applications placed in Yellow/Red queues.
Generates secure, single-use, time-bound (72 hours) re-upload tokens and
simulates multi-channel (SMS & WhatsApp via CDAC) notification dispatch.
"""

import time
import secrets
import hashlib
from typing import Dict, Any

class DeficiencyWorkflowManager:
    def __init__(self):
        # In-memory token repository {token: metadata}
        self.active_deficiency_tokens = {}

    def generate_reupload_token(self, application_id: str, student_phone: str, defective_docs: list, reason: str) -> Dict[str, Any]:
        """
        Creates a 72-hour cryptographically secure re-upload link.
        """
        token = secrets.token_urlsafe(32)
        expiry_timestamp = int(time.time()) + (72 * 3600) # 72 hours from now

        record = {
            "token": token,
            "application_id": application_id,
            "student_phone": student_phone,
            "defective_docs": defective_docs,
            "reason": reason,
            "created_at": int(time.time()),
            "expires_at": expiry_timestamp,
            "is_used": False,
            "reupload_url": f"https://tribalsetu.mota.gov.in/reupload?token={token}"
        }
        self.active_deficiency_tokens[token] = record

        # Simulated CDAC SMS / WhatsApp Payload
        sms_text = (
            f"[MoTA TribalSetu] Action Required for App #{application_id}. "
            f"Your document ({', '.join(defective_docs)}) needs clarification: {reason}. "
            f"Upload clear copy within 72 hrs: {record['reupload_url']}"
        )

        return {
            "success": True,
            "token": token,
            "expires_in_hours": 72,
            "expiry_timestamp": expiry_timestamp,
            "reupload_url": record["reupload_url"],
            "dispatch_channels": {
                "sms_cdac": {"status": "DISPATCHED", "phone_masked": f"+91-XXXXX-{student_phone[-4:]}", "message": sms_text},
                "whatsapp_business": {"status": "DELIVERED", "template": "scholarship_deficiency_alert"}
            }
        }

    def validate_and_consume_token(self, token: str) -> Dict[str, Any]:
        """Validates if token is valid, unused, and within 72h window"""
        record = self.active_deficiency_tokens.get(token)
        if not record:
            return {"valid": False, "error": "Invalid or expired re-upload token."}

        if record["is_used"]:
            return {"valid": False, "error": "This re-upload token has already been consumed."}

        if int(time.time()) > record["expires_at"]:
            return {"valid": False, "error": "Token has expired (>72 hours). Please visit District Welfare Office."}

        return {"valid": True, "record": record}

    def mark_token_used(self, token: str):
        if token in self.active_deficiency_tokens:
            self.active_deficiency_tokens[token]["is_used"] = True

deficiency_manager = DeficiencyWorkflowManager()
