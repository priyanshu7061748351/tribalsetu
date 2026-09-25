"""
Deficiency Re-upload & Automated Notification Engine
Module: ai_engine/deficiency_flow.py

Solves Problem Statement issue:
"repeated correspondence and multiple levels of verification, resulting in processing delays"

Handles:
- Yellow / Red queue deficiency flagging
- Secure 72-hour single-use token generation
- Simulated SMS / WhatsApp / Email notification dispatch via CDAC gateway
- Granular single-document re-upload (without refilling the entire application)
"""

import uuid
import time
from typing import Dict, Any, List


class DeficiencyWorkflowManager:
    """
    Manages application deficiency tickets, secure re-upload tokens, and applicant alerts.
    """

    def __init__(self):
        # In-memory deficiency token store: {token: ticket_metadata}
        self.active_tokens: Dict[str, Dict[str, Any]] = {}

    def create_deficiency_ticket(
        self,
        application_id: str,
        applicant_name: str,
        phone_number: str,
        deficient_document_type: str,
        deficiency_reason: str,
        officer_notes: str = "",
        expiry_hours: int = 72
    ) -> Dict[str, Any]:
        """
        Creates a targeted deficiency ticket and issues a secure single-use re-upload link.
        """
        token = str(uuid.uuid4()).replace("-", "")[:24]
        created_at = time.time()
        expires_at = created_at + (expiry_hours * 3600)

        ticket = {
            "ticket_id": f"DEF-{application_id[-6:]}-{token[:6].upper()}",
            "token": token,
            "application_id": application_id,
            "applicant_name": applicant_name,
            "phone_number": phone_number,
            "document_type": deficient_document_type,
            "reason": deficiency_reason,
            "officer_notes": officer_notes or "Please provide a clear, un-tampered copy with readable government seal.",
            "status": "AWAITING_REUPLOAD",
            "created_at": created_at,
            "expires_at": expires_at,
            "reupload_url": f"http://127.0.0.1:8000/reupload/{token}"
        }

        self.active_tokens[token] = ticket

        # Generate simulated multi-channel notifications
        notifications = self._dispatch_simulated_alerts(ticket)

        return {
            "success": True,
            "ticket": ticket,
            "notifications_dispatched": notifications
        }

    def _dispatch_simulated_alerts(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulates SMS and WhatsApp delivery via Gov CDAC / Sandes gateway.
        """
        sms_text = (
            f"[MoTA TribalSetu] Dear {ticket['applicant_name']}, action required for App #{ticket['application_id']}. "
            f"Your {ticket['document_type']} requires re-upload: {ticket['reason']}. "
            f"Upload within 72 hrs: {ticket['reupload_url']}"
        )

        whatsapp_text = (
            f"*Ministry of Tribal Affairs -- Scholarship Scrutiny Notice*\n\n"
            f"Namaskar *{ticket['applicant_name']}*,\n"
            f"Your application *#{ticket['application_id']}* was reviewed by the District Welfare Officer.\n\n"
            f"[!] Issue Identified: {ticket['reason']}\n"
            f"[*] Document Required: {ticket['document_type']}\n"
            f"[-] Valid Till: 72 Hours\n\n"
            f"[>] 1-Click Re-upload Link: {ticket['reupload_url']}\n"
            f"_(You do not need to re-fill your entire form)_"
        )

        return {
            "sms": {
                "channel": "CDAC_SMS_GATEWAY",
                "recipient": ticket["phone_number"],
                "content": sms_text,
                "status": "SENT_DELIVERED"
            },
            "whatsapp": {
                "channel": "SANDES_WHATSAPP_API",
                "recipient": ticket["phone_number"],
                "content": whatsapp_text,
                "status": "SENT_READ"
            }
        }

    def validate_reupload_token(self, token: str) -> Dict[str, Any]:
        """
        Validates whether a re-upload link is active and not expired.
        """
        if token not in self.active_tokens:
            return {"valid": False, "reason": "Invalid or expired re-upload token."}

        ticket = self.active_tokens[token]
        if time.time() > ticket["expires_at"]:
            return {"valid": False, "reason": "This re-upload link has expired (72-hour window lapsed)."}

        if ticket["status"] == "RESOLVED":
            return {"valid": False, "reason": "This deficiency has already been resolved and re-uploaded."}

        return {"valid": True, "ticket": ticket}

    def process_reuploaded_document(self, token: str, reuploaded_filename: str) -> Dict[str, Any]:
        """
        Marks deficiency as resolved and routes back to the verification pipeline.
        """
        val = self.validate_reupload_token(token)
        if not val["valid"]:
            return val

        ticket = self.active_tokens[token]
        ticket["status"] = "RESOLVED"
        ticket["resolved_at"] = time.time()
        ticket["reuploaded_file"] = reuploaded_filename

        return {
            "success": True,
            "message": f"Document '{reuploaded_filename}' received successfully. Re-routed to AI verification queue.",
            "ticket": ticket
        }


# Singleton instance
deficiency_manager = DeficiencyWorkflowManager()


if __name__ == "__main__":
    print("--- Running Self-Test for Deficiency Workflow Engine ---")

    # Create test deficiency ticket
    res = deficiency_manager.create_deficiency_ticket(
        application_id="APP-2026-002",
        applicant_name="Suresh Oraon",
        phone_number="+91 9876543210",
        deficient_document_type="Income Certificate",
        deficiency_reason="Blurry stamp detected by AI preprocessor (Sauvola threshold failure)",
        officer_notes="Please upload a clearer scan where the Tehsildar seal is legible."
    )

    t = res["ticket"]
    token = t["token"]
    print(f"\nTicket Created: {t['ticket_id']}")
    print(f"Re-Upload URL: {t['reupload_url']}")
    print("\nSimulated WhatsApp Notification:\n" + res["notifications_dispatched"]["whatsapp"]["content"])

    # Validate token
    val = deficiency_manager.validate_reupload_token(token)
    print("\nToken Validation:", "PASS" if val["valid"] else "FAIL")

    # Process re-upload
    res_upload = deficiency_manager.process_reuploaded_document(token, "suresh_clean_income_cert.pdf")
    print("Process Re-upload:", res_upload["message"])
