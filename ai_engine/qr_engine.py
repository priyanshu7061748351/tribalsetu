"""
QR Code Payload Reader
Function 3: scan_and_verify_qr()
Scans and decodes certificate QR payloads. It does not authenticate an issuer
signature without a configured trusted public key.
"""

import cv2
import numpy as np
import json

def scan_and_verify_qr(image_cv2: np.ndarray) -> dict:
    """
    Detects and decodes QR codes on government certificates using OpenCV QRCodeDetector.
    Scans both the full image and cropped regions (bottom-right / bottom-left quadrants).
    """
    detector = cv2.QRCodeDetector()
    data, bbox, _ = detector.detectAndDecode(image_cv2)

    # Fallback to search quadrants if whole-image detection misses small QR
    if not data:
        h, w = image_cv2.shape[:2]
        # Search bottom-right quadrant (common standard for Indian certificates)
        br_quad = image_cv2[int(h * 0.5):, int(w * 0.45):]
        data, bbox, _ = detector.detectAndDecode(br_quad)
        
        # Search bottom-left quadrant
        if not data:
            bl_quad = image_cv2[int(h * 0.5):, :int(w * 0.55)]
            data, bbox, _ = detector.detectAndDecode(bl_quad)

    if not data or not data.strip():
        return {
            "qr_present": False,
            "is_digitally_signed": False,
            "official_data": None,
            "verification_status": "NO_QR_DETECTED",
            "message": "No QR code found on the document (Old/Handwritten or crop issue)."
        }

    # Decode payload fields. Signature validation requires a trusted issuer key;
    # this prototype does not have one configured, so it never claims a signature is valid.
    parsed_data = {}
    signature_present = False

    try:
        # Check if JSON payload
        raw = data.strip()
        if raw.startswith("{") and raw.endswith("}"):
            parsed_data = json.loads(raw)
            sig = parsed_data.get("digital_signature") or parsed_data.get("sig", "")
            signature_present = bool(sig)
        else:
            # Key-Value format e.g. "CERT:JH/2024/ST/1029|NAME:Rahul Munda"
            parts = raw.split("|")
            for p in parts:
                if ":" in p:
                    k, v = p.split(":", 1)
                    parsed_data[k.strip().lower()] = v.strip()
            signature_present = bool(parsed_data.get("digital_signature") or parsed_data.get("sig"))

    except Exception:
        parsed_data = {"raw_payload": data}
        signature_present = False

    return {
        "qr_present": True,
        "is_digitally_signed": False,
        "signature_present": signature_present,
        "official_data": parsed_data,
        "verification_status": "SIGNATURE_UNVERIFIED",
        "message": "QR payload decoded, but its signature was not verified against a trusted issuer key."
    }
