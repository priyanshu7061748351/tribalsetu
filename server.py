"""
TribalSetu - FastAPI Backend Server
Serves AI Verification APIs, Schemes Directory, and the Live Web Dashboard.
"""

import json
import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

from ai_engine.pipeline import run_verification_pipeline
from ai_engine.preprocessor import preprocess_and_deskew
from ai_engine.ela_tamper import detect_tampering_ela
from ai_engine.qr_engine import scan_and_verify_qr
from ai_engine.ocr_engine import extract_document_fields
from ai_engine.identity_matcher import cross_match_identity
from ai_engine.dbt_checker import check_dbt_seeding_status
from ai_engine.st_gazette import st_validator
from ai_engine.rule_engine import rule_engine
from ai_engine.merit_allocator import merit_allocator
from ai_engine.deficiency_flow import deficiency_manager
from ai_engine.fellowship_portal import fellowship_manager
from ai_engine.biometrics import biometric_engine
from ai_engine.audit_ledger import audit_ledger, aadhaar_vault

app = FastAPI(
    title="TribalSetu - AI Scholarship & Fellowship Management System",
    description="Ministry of Tribal Affairs (MoTA) Automated Verification & Triaging Engine (SIH26239)",
    version="1.0.0"
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
SAMPLE_DIR = BASE_DIR / "sample_docs"

STATIC_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# Local prototype persistence. Use PostgreSQL and managed secrets before deployment.
DATABASE_PATH = DATA_DIR / "tribalsetu.sqlite3"
OFFICER_SESSION_COOKIE = "tribalsetu_officer_session"
OFFICER_SESSION_TTL_SECONDS = 8 * 60 * 60
OFFICER_LOGIN_WINDOW_SECONDS = 15 * 60
OFFICER_MAX_LOGIN_FAILURES = 10
OFFICER_BOOTSTRAP_TOKEN = os.environ.get("TRIBALSETU_BOOTSTRAP_TOKEN", "")
SESSION_SECRET = os.environ.get("TRIBALSETU_SESSION_SECRET", "")
if SESSION_SECRET and len(SESSION_SECRET.encode("utf-8")) < 32:
    raise RuntimeError("TRIBALSETU_SESSION_SECRET must be at least 32 bytes.")
if not SESSION_SECRET:
    # Local-only fallback: all sessions are invalidated whenever the process restarts.
    SESSION_SECRET = secrets.token_urlsafe(48)


@contextmanager
def _db_connect() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _initialize_storage() -> None:
    with _db_connect() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS officer_users (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS officer_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES officer_users(user_id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS officer_login_attempts (
                client_key TEXT NOT NULL,
                failed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS applications (
                application_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS application_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id TEXT NOT NULL,
                officer_user_id TEXT,
                officer_email TEXT,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(application_id) REFERENCES applications(application_id)
            );
            CREATE INDEX IF NOT EXISTS idx_applications_status_created
                ON applications(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_application_events_application
                ON application_events(application_id, event_id);
            CREATE INDEX IF NOT EXISTS idx_officer_sessions_user_expiry
                ON officer_sessions(user_id, expires_at);
            CREATE INDEX IF NOT EXISTS idx_officer_login_attempts_client_time
                ON officer_login_attempts(client_key, failed_at);
        """)


_initialize_storage()
verification_tickets = {}
VERIFICATION_TICKET_TTL_SECONDS = 15 * 60
MAX_ACTIVE_VERIFICATION_TICKETS = 1000
MAX_VERIFICATION_DOCUMENT_BYTES = 10 * 1024 * 1024


class OfficerBootstrapRequest(BaseModel):
    setup_token: str
    full_name: str
    email: str
    password: str


class OfficerLoginRequest(BaseModel):
    email: str
    password: str


class OfficerDecisionRequest(BaseModel):
    action: str
    reason: str


def _password_hash(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600_000)
    return "pbkdf2_sha256$600000${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


_DUMMY_PASSWORD_HASH = _password_hash("not-a-valid-officer-password")


def _verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _sign_session(user_id: str) -> str:
    issued_at = int(time.time())
    payload = json.dumps(
        {"sub": user_id, "exp": issued_at + OFFICER_SESSION_TTL_SECONDS, "jti": secrets.token_urlsafe(12)},
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    signature = hmac.new(SESSION_SECRET.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{encoded_payload}.{encoded_signature}"


def _read_session(request: Request) -> Optional[dict]:
    token = request.cookies.get(OFFICER_SESSION_COOKIE, "")
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(SESSION_SECRET.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
        supplied_signature = base64.urlsafe_b64decode(encoded_signature + "=" * (-len(encoded_signature) % 4))
        if not hmac.compare_digest(expected_signature, supplied_signature):
            return None
        payload_bytes = base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4))
        payload = json.loads(payload_bytes.decode("utf-8"))
        if int(payload.get("exp", 0)) <= int(time.time()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _officer_from_request(request: Request) -> Optional[dict]:
    session = _read_session(request)
    if not session or not session.get("sub"):
        return None
    token_hash = hashlib.sha256(request.cookies.get(OFFICER_SESSION_COOKIE, "").encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    with _db_connect() as connection:
        officer = connection.execute(
            """SELECT u.user_id, u.email, u.full_name, u.role
               FROM officer_users u
               JOIN officer_sessions s ON s.user_id = u.user_id
               WHERE u.user_id = ? AND u.is_active = 1 AND s.token_hash = ? AND s.expires_at > ?""",
            (session["sub"], token_hash, now),
        ).fetchone()
    return dict(officer) if officer else None


def _require_officer(request: Request) -> dict:
    officer = _officer_from_request(request)
    if not officer:
        raise HTTPException(status_code=401, detail="Officer login is required.")
    return officer


def _set_officer_cookie(response: Response, request: Request, user_id: str) -> None:
    token = _sign_session(user_id)
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(seconds=OFFICER_SESSION_TTL_SECONDS)
    with _db_connect() as connection:
        connection.execute("DELETE FROM officer_sessions WHERE expires_at <= ?", (created_at.isoformat(),))
        connection.execute(
            "INSERT INTO officer_sessions(token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (hashlib.sha256(token.encode("utf-8")).hexdigest(), user_id, expires_at.isoformat(), created_at.isoformat()),
        )
    response.set_cookie(
        OFFICER_SESSION_COOKIE,
        token,
        max_age=OFFICER_SESSION_TTL_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )


def _store_application(application: dict) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    with _db_connect() as connection:
        connection.execute(
            "INSERT INTO applications(application_id, payload_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (application["id"], json.dumps(application, ensure_ascii=False), application["status"], timestamp, timestamp),
        )
        connection.execute(
            "INSERT INTO application_events(application_id, action, reason, created_at) VALUES (?, ?, ?, ?)",
            (application["id"], "SUBMITTED", "Application submitted for human officer review.", timestamp),
        )


def _masked_aadhaar(value: str) -> str:
    digits = "".join(character for character in str(value) if character.isdigit())
    return f"XXXX-XXXX-{digits[-4:]}" if len(digits) >= 4 else "XXXX-XXXX-XXXX"


def _purge_expired_verification_tickets() -> None:
    now = time.monotonic()
    expired = [token for token, ticket in verification_tickets.items() if ticket["expires_at"] <= now]
    for token in expired:
        verification_tickets.pop(token, None)


def _login_client_key(request: Request) -> str:
    address = request.client.host if request.client else "unknown"
    return hmac.new(SESSION_SECRET.encode("utf-8"), address.encode("utf-8"), hashlib.sha256).hexdigest()


# --- TRIAL PAGE: 4-in-1 Document Verifier ---
@app.get("/trial", response_class=HTMLResponse)
@app.get("/trial/", response_class=HTMLResponse)
@app.get("/trial.html", response_class=HTMLResponse)
@app.get("/tria", response_class=HTMLResponse)
async def trial_page():
    trial_file = STATIC_DIR / "trial.html"
    if trial_file.exists():
        with open(trial_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>trial.html not found in static/</h1>"

# --- VERHOEFF ALGORITHM FOR AADHAAR CHECKSUM ---
VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
]
VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]
]

def validate_verhoeff_checksum(aadhaar_num: str) -> bool:
    clean = "".join(filter(str.isdigit, str(aadhaar_num)))
    if len(clean) != 12:
        return False
    c = 0
    for i, item in enumerate(reversed(clean)):
        c = VERHOEFF_D[c][VERHOEFF_P[i % 8][int(item)]]
    return c == 0

@lru_cache(maxsize=1)
def _load_trial_ocr_engine():
    """Load a local OCR engine with English/Devanagari recognition models."""
    from rapidocr import RapidOCR
    from rapidocr.utils.typings import ModelType, OCRVersion
    return RapidOCR(params={
        "Det.lang_type": "multi",
        "Det.model_type": ModelType.MOBILE,
        "Det.ocr_version": OCRVersion.PPOCRV4,
        "Rec.lang_type": "devanagari",
        "Rec.model_type": ModelType.MOBILE,
        "Rec.ocr_version": OCRVersion.PPOCRV4
    })


@app.post("/api/trial-verify")
async def trial_verify(
    document: UploadFile = File(...),
    doc_type: str = Form("caste"),
    issuer_state: str = Form("bihar")
):
    """Read a document and return review signals, never an automated fraud verdict."""
    import io
    import re
    from urllib.parse import urlsplit
    from PIL import Image

    allowed_doc_types = {"aadhaar", "caste", "income", "residence", "domicile"}
    if doc_type not in allowed_doc_types:
        raise HTTPException(status_code=422, detail="Unsupported document category.")
    if issuer_state not in {"bihar", "other"}:
        raise HTTPException(status_code=422, detail="Unsupported issuing-state selection.")

    raw_bytes = await document.read(MAX_VERIFICATION_DOCUMENT_BYTES + 1)
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty; no authenticity or eligibility finding was made.")
    if len(raw_bytes) > MAX_VERIFICATION_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="The file exceeds the 10 MB limit; no authenticity or eligibility finding was made.")

    is_pdf = raw_bytes.startswith(b"%PDF")
    image_format = ""
    pdf_page_count = None
    pdf_pages_analyzed = None
    embedded_pdf_text = ""
    analysis_images = []

    if is_pdf:
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise HTTPException(
                status_code=503,
                detail="PDF reading is unavailable on this server. No authenticity or eligibility finding was made."
            ) from exc
        pdf = None
        try:
            pdf = pdfium.PdfDocument(raw_bytes)
            pdf_page_count = len(pdf)
            if pdf_page_count < 1:
                raise ValueError("The PDF has no pages.")
            pdf_pages_analyzed = min(pdf_page_count, 5)
            text_pages = []
            for page_index in range(pdf_pages_analyzed):
                page = pdf[page_index]
                try:
                    try:
                        text_page = page.get_textpage()
                        try:
                            page_text = text_page.get_text_bounded()
                            if page_text and page_text.strip():
                                text_pages.append(page_text.strip())
                        finally:
                            text_page.close()
                    except Exception:
                        pass

                    # Keep one rendered page per analyzed page for QR/OCR.
                    # The first page uses higher resolution for certificate text.
                    render_scale = 2.5 if page_index == 0 else 1.5
                    page_image = page.render(scale=render_scale).to_pil().convert("RGB")
                    rendered = io.BytesIO()
                    page_image.save(rendered, format="PNG")
                    analysis_images.append(rendered.getvalue())
                finally:
                    page.close()
            embedded_pdf_text = "\n".join(text_pages)
            image_format = "PDF"
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail="The PDF could not be read or rendered. No authenticity or eligibility finding was made."
            ) from exc
        finally:
            if pdf is not None:
                pdf.close()
    else:
        try:
            with Image.open(io.BytesIO(raw_bytes)) as probe:
                image_format = (probe.format or "").upper()
                probe.verify()
            with Image.open(io.BytesIO(raw_bytes)) as source_image:
                image = source_image.convert("RGB")
                normalized = io.BytesIO()
                image.save(normalized, format="PNG")
                analysis_images.append(normalized.getvalue())
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail="The upload is not a readable PDF or supported image. No authenticity or eligibility finding was made."
            ) from exc

    analysis_bytes = analysis_images[0]

    # ELA is only a heuristic on an original JPEG image. PDF renders and other
    # formats do not support this comparison and receive no ELA verdict.
    ela_status = "NOT_APPLICABLE"
    ela_explanation = "ELA is limited to JPEG compression signals and cannot establish authenticity."
    ela_heatmap = ""
    ela_signal_score = None
    if not is_pdf and image_format in {"JPEG", "JPG"}:
        try:
            from ai_engine.ela_tamper import detect_tampering_ela
            ela_result = detect_tampering_ela(raw_bytes)
            if not str(ela_result.get("explanation", "")).startswith("Error parsing image:"):
                ela_status = "SIGNAL_ONLY"
                ela_explanation = (
                    "A JPEG compression signal was generated. It is a heuristic and must not be used "
                    "alone to label a document fake or genuine."
                )
                ela_signal_score = ela_result.get("tamper_score")
                ela_heatmap = ela_result.get("heatmap_base64", "") or ""
            else:
                ela_status = "UNAVAILABLE"
                ela_explanation = "ELA could not analyze this image; no authenticity finding was made."
        except Exception:
            ela_status = "UNAVAILABLE"
            ela_explanation = "ELA could not analyze this image; no authenticity finding was made."

    # Search every analyzed page for QR presence. No issuer signature or
    # certificate authority database is configured by this prototype.
    qr_status = "UNAVAILABLE"
    qr_is_gov_domain = False
    try:
        import cv2
        import numpy as np
        qr_status = "NOT_FOUND"
        for page_bytes in analysis_images:
            image_array = cv2.imdecode(np.frombuffer(page_bytes, np.uint8), cv2.IMREAD_COLOR)
            if image_array is None:
                continue
            decoded_payload = ""
            try:
                import zxingcpp
                barcodes = zxingcpp.read_barcodes(image_array)
                if barcodes:
                    decoded_payload = barcodes[0].text or ""
            except Exception:
                pass
            if not decoded_payload:
                decoded_payload, _, _ = cv2.QRCodeDetector().detectAndDecode(image_array)
            if decoded_payload:
                qr_status = "FOUND_UNVERIFIED"
                parsed_url = urlsplit(decoded_payload)
                host = (parsed_url.hostname or "").lower()
                qr_is_gov_domain = host == "gov.in" or host.endswith(".gov.in")
                break
    except Exception:
        pass

    # Prefer Unicode text embedded in digital PDFs; run the local OCR model for
    # scanned pages and ordinary images. No raw text/full Aadhaar is returned.
    ocr_fragments = [embedded_pdf_text] if embedded_pdf_text else []
    ocr_engine_status = "NOT_NEEDED" if embedded_pdf_text else "NOT_LOADED"
    should_run_ocr = not embedded_pdf_text or len(embedded_pdf_text.strip()) < 60
    if should_run_ocr:
        try:
            import cv2
            import numpy as np
            ocr_engine = _load_trial_ocr_engine()
            ocr_engine_status = "READY"
            for page_bytes in analysis_images:
                image_array = cv2.imdecode(np.frombuffer(page_bytes, np.uint8), cv2.IMREAD_COLOR)
                if image_array is None:
                    continue
                result = ocr_engine(image_array)
                recognized_lines = getattr(result, "txts", None)
                if recognized_lines is None and isinstance(result, tuple) and result:
                    recognized_lines = result[0]
                if recognized_lines:
                    lines = []
                    for item in recognized_lines:
                        if isinstance(item, str):
                            lines.append(item)
                        elif isinstance(item, (list, tuple)) and len(item) > 1 and isinstance(item[1], str):
                            lines.append(item[1])
                    if lines:
                        ocr_fragments.append("\n".join(lines))
        except Exception:
            ocr_engine_status = "UNAVAILABLE"

    ocr_text = "\n".join(part for part in ocr_fragments if part and part.strip()).strip()
    if embedded_pdf_text and len(ocr_fragments) > 1:
        ocr_source = "PDF text layer + local OCR"
    elif embedded_pdf_text:
        ocr_source = "PDF text layer"
    elif ocr_text:
        ocr_source = "Local OCR (candidate text)"
    else:
        ocr_source = "No text extracted"

    extracted_fields = {}
    name_match = re.search(
        r"(?:name\s+of\s+(?:the\s+)?applicant|applicant\s*name|name|नाम)\s*[:.-]?\s*([^\r\n]{2,80})",
        ocr_text,
        re.IGNORECASE
    )
    if name_match:
        candidate = name_match.group(1)
        candidate = re.split(r"\b(?:father|s/o|d/o|w/o|caste|tribe|certificate\s*(?:no|number))\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0]
        candidate = candidate.strip(" :-.\t")
        if candidate:
            extracted_fields["name"] = candidate[:80]
    else:
        prose_name = re.search(
            r"(?:this\s+is\s+to\s+certify\s+that\s+)?(?:shri|smt\.?|kumari|miss|mr\.?|mrs\.?)\s+([A-Za-z][A-Za-z .'-]{1,60}?)\s+(?:son|daughter|wife)\s+of",
            ocr_text,
            re.IGNORECASE
        )
        if prose_name:
            extracted_fields["name"] = prose_name.group(1).strip()

    father_match = re.search(
        r"(?:father(?:'s)?\s*(?:name)?|s/o|d/o|पिता(?:\s*का\s*नाम)?)\s*[:.-]?\s*([^\r\n]{2,80})",
        ocr_text,
        re.IGNORECASE
    )
    if father_match:
        candidate = re.split(r"\b(?:mother|village|post|district|dist|caste|tribe)\b", father_match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
        candidate = candidate.strip(" :-.\t")
        if candidate:
            extracted_fields["father_name"] = candidate[:80]
    else:
        prose_father = re.search(
            r"(?:son|daughter|wife)\s+of\s+(?:shri|smt\.?|mr\.?|mrs\.?)?\s*([A-Za-z][A-Za-z .'-]{1,60}?)(?:\s+(?:of|resident|village|district|caste|tribe)\b|[\r\n,.]|$)",
            ocr_text,
            re.IGNORECASE
        )
        if prose_father:
            extracted_fields["father_name"] = prose_father.group(1).strip()

    field_patterns = {
        "certificate_no": r"(?:certificate\s*(?:no\.?|number|id|#)|cert\.?\s*(?:no\.?|number|id|#)|application\s*(?:no\.?|number|id|#))\s*[:.-]?\s*([A-Za-z0-9][A-Za-z0-9/\-_]{2,47})",
        "annual_income": r"(?:annual\s*income|family\s*income|income|वार्षिक\s*आय|आय)\s*[:.-]?\s*(?:rs\.?|₹)?\s*([0-9,]+)",
        "issue_date": r"(?:date\s+of\s+issue|issue\s+date|issued\s+on|जारी\s*दिनांक)\s*[:.-]?\s*(\d{1,2}[/-](?:\d{1,2}|[A-Za-z]{3})[/-]\d{2,4})"
    }
    for field, pattern in field_patterns.items():
        match = re.search(pattern, ocr_text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            extracted_fields[field] = f"₹{value}" if field == "annual_income" else value

    aadhaar_match = re.search(r"(?<!\d)(\d{4})\s*(\d{4})\s*(\d{4})(?!\d)", ocr_text)
    masked_aadhaar = f"XXXX-XXXX-{aadhaar_match.group(3)}" if aadhaar_match else None
    if masked_aadhaar:
        extracted_fields["masked_aadhaar"] = masked_aadhaar

    category_match = re.search(
        r"(scheduled\s*tribe|अनुसूचित\s*जनजाति|\bST\b|other\s*backward\s*class|\bOBC\b|scheduled\s*caste|\bSC\b)",
        ocr_text,
        re.IGNORECASE
    )
    if category_match:
        extracted_fields["category"] = category_match.group(1)

    known_tribes = [
        "munda", "santhal", "santal", "oraon", "ho", "kharia", "bhil", "gond",
        "bodo", "meena", "baiga", "kondh", "kawar", "kisan", "asur", "birhor"
    ]
    for tribe in known_tribes:
        if re.search(r"\b" + re.escape(tribe) + r"\b", ocr_text, re.IGNORECASE):
            extracted_fields["detected_tribe"] = tribe.title()
            break

    ocr_status = "TEXT_EXTRACTED" if ocr_text else ("ENGINE_UNAVAILABLE" if ocr_engine_status == "UNAVAILABLE" else "NO_TEXT_EXTRACTED")
    ocr_detail = f"Text source: {ocr_source}. These are provisional OCR candidates; compare them with the uploaded document."
    if ocr_engine_status == "UNAVAILABLE" and not embedded_pdf_text:
        ocr_detail = "The local OCR engine or its model is unavailable. No text or authenticity conclusion was produced."

    stages = [
        {"stage": 1, "id": "file_read", "name": "File Read", "status": "INFO", "badge": "Decoded", "detail": f"The file was decoded. Analysis scope: {min(pdf_pages_analyzed, pdf_page_count)} of {pdf_page_count} PDF page(s)." if is_pdf else "The image was decoded for local screening. This does not validate its source."},
        {"stage": 2, "id": "ela_signal", "name": "ELA Image Signal", "status": "WARN", "badge": ela_status.replace("_", " "), "detail": ela_explanation},
        {"stage": 3, "id": "qr_presence", "name": "QR Presence", "status": "WARN", "badge": qr_status.replace("_", " "), "detail": "QR presence is not a digital signature check. Issuing-authority verification is not connected."},
        {"stage": 4, "id": "ocr_candidates", "name": "OCR Candidate Fields", "status": "INFO" if ocr_text else "WARN", "badge": "Text extracted" if ocr_text else ("OCR unavailable" if ocr_status == "ENGINE_UNAVAILABLE" else "No text extracted"), "detail": ocr_detail},
        {"stage": 5, "id": "eligibility", "name": "Scheme Eligibility", "status": "WARN", "badge": "Not assessed", "detail": "Eligibility needs the selected scheme rules, state, and officer review."},
        {"stage": 6, "id": "identity", "name": "Identity Cross-Check", "status": "WARN", "badge": "Not checked", "detail": "No comparison against separate identity or academic records was performed."},
        {"stage": 7, "id": "dbt", "name": "DBT / Bank Status", "status": "WARN", "badge": "Not checked", "detail": "No bank, Aadhaar Payment Bridge, or government DBT system was accessed."},
        {"stage": 8, "id": "review", "name": "Review Routing", "status": "WARN", "badge": "Officer review required", "detail": "No trust score or automated genuine/fake decision is produced by this screening."}
    ]

    if is_pdf:
        scope = f"First {pdf_pages_analyzed} of {pdf_page_count} PDF page(s)" if pdf_page_count > pdf_pages_analyzed else f"All {pdf_page_count} PDF page(s)"
    else:
        scope = "Uploaded image"

    issuer_verification = {
        "status": "MANUAL_PORTAL_AVAILABLE" if issuer_state == "bihar" and doc_type != "aadhaar" else "NOT_CONNECTED",
        "authority": "Bihar RTPS / ServicePlus" if issuer_state == "bihar" and doc_type != "aadhaar" else None,
        "verification_url": "https://rtps.bihar.gov.in/dscertificateview/webcopy/verifyCertificates.aspx" if issuer_state == "bihar" and doc_type != "aadhaar" else None,
        "message": (
            "Open the Bihar Government verifier yourself. This app does not send your document or identifiers, and the issuing authority remains responsible for final verification."
            if issuer_state == "bihar" and doc_type != "aadhaar"
            else "No issuing-authority verification portal is connected for this selection. No authenticity conclusion was made."
        )
    }

    return JSONResponse(content={
        "overall_verdict": "HUMAN_REVIEW_REQUIRED",
        "review_status": "HUMAN_REVIEW_REQUIRED",
        "integrity_score": None,
        "is_genuine": None,
        "decision": "YELLOW",
        "decision_label": "HUMAN_REVIEW_REQUIRED",
        "badge_color": "#F59E0B",
        "doc_type": doc_type,
        "document_format": image_format,
        "pdf_pages_total": pdf_page_count,
        "pdf_pages_analyzed": pdf_pages_analyzed,
        "analysis_scope": scope,
        "issuer_verification": issuer_verification,
        "stages": stages,
        "audit_trail": [
            f"Document text source: {ocr_source}. Raw OCR text was not returned.",
            f"ELA status: {ela_status}. Any ELA signal is heuristic, not proof.",
            f"QR status: {qr_status}. No issuing-authority signature validation was performed.",
            "Eligibility, identity matching, and DBT checks were not performed.",
            "Outcome: officer review required; no fraud or ineligibility finding was made."
        ],
        "checks": {
            "ela_forensics": {
                "status": ela_status,
                "signal_score": ela_signal_score,
                "explanation": ela_explanation,
                "heatmap": ela_heatmap
            },
            "qr_code": {
                "status": qr_status,
                "signature_verified": False,
                "is_gov_domain": qr_is_gov_domain
            },
            "ocr": {
                "status": ocr_status,
                "source": ocr_source,
                "engine_status": ocr_engine_status,
                "pages_analyzed": pdf_pages_analyzed if is_pdf else 1,
                "raw_text_returned": False
            },
            "aadhaar_masking": {
                "status": "MASKED" if masked_aadhaar else "NOT_DETECTED",
                "masked_number": masked_aadhaar,
                "verhoeff_valid": None
            },
            "eligibility": {"status": "NOT_ASSESSED"},
            "identity": {"status": "NOT_CHECKED"},
            "dbt": {"status": "NOT_CHECKED"}
        },
        "extracted_fields": extracted_fields,
        "doc_specific_checks": {"status": "NOT_ASSESSED"}
    })

# Mount static folder
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    index_file = BASE_DIR / "index.html"
    if not index_file.exists():
        index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>TribalSetu Server is running! Place index.html in project folder.</h1>"

@app.get("/api/health")
async def local_health():
    """Identify this local API build for the Windows launcher."""
    return {"service": "tribalsetu-local", "build": "screening-v1", "status": "ok"}

@app.get("/api/schemes")
async def get_schemes():
    """Returns official MoTA scholarship schemes & document checklists"""
    schemes_file = DATA_DIR / "schemes_directory.json"
    if schemes_file.exists():
        with open(schemes_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"schemes": []}

@app.get("/api/dbt-check/{aadhaar}")
async def check_dbt(aadhaar: str):
    """Simulates NPCI Aadhaar-Bank Seeding status check"""
    return check_dbt_seeding_status(aadhaar)

@app.post("/api/verify")
async def verify_certificate(
    caste_doc: UploadFile = File(...),
    applicant_name: str = Form(...),
    aadhaar_no: str = Form(...),
    caste_name: str = Form(""),
    state: str = Form("jharkhand"),
    father_name: str = Form("")
):
    """
    Returns limited screening signals for officer review; it does not decide
    certificate authenticity or scheme eligibility.
    """
    _purge_expired_verification_tickets()
    if len(verification_tickets) >= MAX_ACTIVE_VERIFICATION_TICKETS:
        raise HTTPException(status_code=429, detail="Verification capacity is temporarily full. Try again later.")

    if not aadhaar_no.isdigit() or len(aadhaar_no) != 12:
        raise HTTPException(status_code=400, detail="Aadhaar input must contain exactly 12 digits.")

    doc_bytes = await caste_doc.read(MAX_VERIFICATION_DOCUMENT_BYTES + 1)
    if not doc_bytes:
        raise HTTPException(status_code=400, detail="Empty document file uploaded")
    if len(doc_bytes) > MAX_VERIFICATION_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds the 10 MB upload limit.")

    res = run_verification_pipeline(
        caste_doc_bytes=doc_bytes,
        applicant_name=applicant_name,
        aadhaar_no=aadhaar_no,
        caste_name=caste_name,
        state=state,
        father_name=father_name
    )

    # Keep the application-intake route non-adjudicative too. A local ST-list
    # text mismatch can reflect a BC/OBC category, spelling, or state difference;
    # it cannot establish that a certificate is fake or that a person is ineligible.
    st_reference_match = res.pop("is_st_verified", None)
    res.pop("sub_scores", None)
    res["st_schedule_candidate_match"] = st_reference_match
    res["review_status"] = "HUMAN_REVIEW_REQUIRED"
    res["integrity_score"] = None
    res["trust_score"] = None
    res["decision"] = "YELLOW"
    res["decision_label"] = "HUMAN_REVIEW_REQUIRED"
    res["badge_color"] = "#F59E0B"
    res["summary"] = (
        "This screening reports limited document and text signals only. "
        "An authorized officer must review the original certificate and the selected scheme rules."
    )
    if st_reference_match is True:
        st_reference_note = (
            "The entered or extracted community text matched a local ST-name reference list. "
            "This does not authenticate the certificate or decide scheme eligibility."
        )
    elif st_reference_match is False:
        st_reference_note = (
            "The entered or extracted community text did not match the local ST-name reference list. "
            "A BC/OBC category, spelling difference, or state mismatch can cause this; it does not mean the certificate is fake. "
            "Check the official category and scheme rules with an officer."
        )
    else:
        st_reference_note = "No local ST-name reference result is available; an officer must review the category and scheme rules."

    ela_result = res.get("ela_forensics") or {}
    ela_result["status"] = "SIGNAL_ONLY"
    ela_result["is_tampered"] = None
    ela_result["tamper_score"] = None
    ela_result["explanation"] = (
        "Image-compression analysis is a limited screening signal. It cannot prove that a certificate is genuine or fake."
    )
    res["ela_forensics"] = ela_result

    qr_result = res.get("qr_verification") or {}
    qr_present = bool(qr_result.get("qr_present"))
    res["qr_verification"] = {
        "status": "FOUND_UNVERIFIED" if qr_present else "NOT_FOUND",
        "qr_present": qr_present,
        "signature_verified": False,
        "detail": "QR presence does not verify the issuing authority's signature."
    }
    res["identity_verification"] = {"status": "NOT_CHECKED"}
    res["dbt_status"] = {"status": "NOT_CHECKED"}
    extracted_fields = res.get("extracted_fields") or {}
    extracted_fields.pop("raw_text", None)
    res["extracted_fields"] = extracted_fields
    res["audit_trail"] = [
        "The file was decoded for local screening; this does not validate its issuing authority.",
        "OCR values are provisional candidates and must be compared with the original document.",
        "QR presence and image-compression signals are not proof of authenticity or tampering.",
        st_reference_note,
        "Scheme eligibility, identity records, and DBT/bank status were not verified.",
        "Outcome: officer review required. No authenticity score or automatic eligibility decision was produced."
    ]

    verification_token = secrets.token_urlsafe(32)
    verification_tickets[verification_token] = {
        "expires_at": time.monotonic() + VERIFICATION_TICKET_TTL_SECONDS,
        "applicant_name": applicant_name.strip(),
        "father_name": father_name.strip(),
        "aadhaar_no": _masked_aadhaar(aadhaar_no),
        "caste": res.get("verified_tribe") or caste_name.strip(),
        "state": state.strip(),
        "ai_signal_score": res.get("trust_score"),
        "ai_signal_decision": res.get("decision"),
        "ai_signal_label": res.get("decision_label"),
        "ela_tampering": (res.get("ela_forensics") or {}).get("explanation", "Review required"),
        "audit_trail": res.get("audit_trail", []),
    }
    res["verification_token"] = verification_token
    res["verification_token_expires_in_seconds"] = VERIFICATION_TICKET_TTL_SECONDS

    return JSONResponse(content=res)

@app.post("/api/apply")
async def submit_application(
    verification_token: str = Form(...),
    scheme_name: str = Form(...),
    district: str = Form("")
):
    """Consumes a server-issued verification ticket and queues the case for human review."""
    _purge_expired_verification_tickets()
    ticket = verification_tickets.pop(verification_token, None)
    if not ticket:
        raise HTTPException(
            status_code=400,
            detail="Verification ticket is invalid, expired, or already used. Verify the document again.",
        )

    scheme_name = scheme_name.strip()
    if not scheme_name or len(scheme_name) > 200:
        raise HTTPException(status_code=400, detail="A valid scheme name is required.")

    app_id = f"APP-2026-{secrets.token_hex(8).upper()}"
    now = datetime.now(timezone.utc).astimezone()

    new_app = {
        "id": app_id,
        "applicant_name": ticket["applicant_name"],
        "father_name": ticket["father_name"],
        "aadhaar_no": ticket["aadhaar_no"],
        "caste": ticket["caste"],
        "state": ticket["state"],
        "district": district.strip()[:100],
        "scheme_name": scheme_name,
        "ai_signal_score": ticket["ai_signal_score"],
        "ai_signal_decision": ticket["ai_signal_decision"],
        "decision": "YELLOW",
        "decision_label": "HUMAN_REVIEW_REQUIRED",
        "badge_color": "#F59E0B",
        "status": "PENDING_OFFICER_REVIEW",
        "dbt_status": "NOT_INITIATED",
        "applied_date": now.strftime("%d-%b-%Y"),
        "ela_tampering": ticket["ela_tampering"],
        "audit_trail": ticket["audit_trail"],
    }
    try:
        _store_application(new_app)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Could not save the application. Please verify and submit again.")
    return {"success": True, "application_id": app_id, "application": new_app}


@app.get("/api/auth/status")
async def officer_auth_status(request: Request):
    with _db_connect() as connection:
        officer_count = connection.execute("SELECT COUNT(*) FROM officer_users WHERE is_active = 1").fetchone()[0]
    officer = _officer_from_request(request)
    return {
        "authenticated": officer is not None,
        "officer": officer,
        "setup_required": officer_count == 0,
        "bootstrap_enabled": len(OFFICER_BOOTSTRAP_TOKEN) >= 32,
        "session_secret_ephemeral": not bool(os.environ.get("TRIBALSETU_SESSION_SECRET")),
    }


@app.post("/api/auth/bootstrap")
async def bootstrap_first_officer(payload: OfficerBootstrapRequest, request: Request, response: Response):
    if len(OFFICER_BOOTSTRAP_TOKEN) < 32:
        raise HTTPException(status_code=503, detail="First-officer setup is disabled. Configure a 32-character TRIBALSETU_BOOTSTRAP_TOKEN on the server.")
    if not hmac.compare_digest(payload.setup_token, OFFICER_BOOTSTRAP_TOKEN):
        raise HTTPException(status_code=403, detail="Setup token is invalid.")
    full_name = payload.full_name.strip()
    email = payload.email.strip().lower()
    password = payload.password
    if not full_name or len(full_name) > 120 or "@" not in email or len(email) > 254:
        raise HTTPException(status_code=400, detail="Enter a valid officer name and email address.")
    if len(password) < 12 or len(password) > 256:
        raise HTTPException(status_code=400, detail="Officer password must be between 12 and 256 characters.")

    user_id = secrets.token_urlsafe(18)
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with _db_connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            count = connection.execute("SELECT COUNT(*) FROM officer_users WHERE is_active = 1").fetchone()[0]
            if count:
                raise HTTPException(status_code=409, detail="First-officer setup has already been completed.")
            connection.execute(
                "INSERT INTO officer_users(user_id, email, full_name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, email, full_name, "MOTA_ADMIN", _password_hash(password), created_at),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An officer account with this email already exists.")

    _set_officer_cookie(response, request, user_id)
    return {"success": True, "officer": {"user_id": user_id, "email": email, "full_name": full_name, "role": "MOTA_ADMIN"}}


@app.post("/api/auth/login")
async def officer_login(payload: OfficerLoginRequest, request: Request, response: Response):
    email = payload.email.strip().lower()
    if len(email) > 254 or len(payload.password) > 256:
        raise HTTPException(status_code=400, detail="Email or password is too long.")
    client_key = _login_client_key(request)
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(seconds=OFFICER_LOGIN_WINDOW_SECONDS)).isoformat()
    with _db_connect() as connection:
        connection.execute("DELETE FROM officer_login_attempts WHERE failed_at < ?", (cutoff,))
        failures = connection.execute(
            "SELECT COUNT(*) FROM officer_login_attempts WHERE client_key = ? AND failed_at >= ?",
            (client_key, cutoff),
        ).fetchone()[0]
        if failures >= OFFICER_MAX_LOGIN_FAILURES:
            raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait 15 minutes and try again.")
        officer = connection.execute(
            "SELECT user_id, email, full_name, role, password_hash FROM officer_users WHERE email = ? AND is_active = 1",
            (email,),
        ).fetchone()
    encoded_hash = officer["password_hash"] if officer else _DUMMY_PASSWORD_HASH
    if not _verify_password(payload.password, encoded_hash):
        with _db_connect() as connection:
            connection.execute(
                "INSERT INTO officer_login_attempts(client_key, failed_at) VALUES (?, ?)",
                (client_key, now.isoformat()),
            )
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    with _db_connect() as connection:
        connection.execute("DELETE FROM officer_login_attempts WHERE client_key = ?", (client_key,))
    _set_officer_cookie(response, request, officer["user_id"])
    return {"success": True, "officer": {"user_id": officer["user_id"], "email": officer["email"], "full_name": officer["full_name"], "role": officer["role"]}}


@app.post("/api/auth/logout")
async def officer_logout(request: Request, response: Response):
    token = request.cookies.get(OFFICER_SESSION_COOKIE, "")
    if token:
        with _db_connect() as connection:
            connection.execute(
                "DELETE FROM officer_sessions WHERE token_hash = ?",
                (hashlib.sha256(token.encode("utf-8")).hexdigest(),),
            )
    response.delete_cookie(OFFICER_SESSION_COOKIE, path="/", httponly=True, samesite="strict")
    return {"success": True}


@app.get("/api/applications")
async def get_applications(request: Request):
    _require_officer(request)
    with _db_connect() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM applications ORDER BY created_at DESC"
        ).fetchall()
    return {"applications": [json.loads(row["payload_json"]) for row in rows]}


@app.get("/api/applications/{app_id}/status")
async def get_application_status(app_id: str):
    """Return a minimal status view for the applicant holding the tracking ID."""
    with _db_connect() as connection:
        row = connection.execute(
            "SELECT payload_json FROM applications WHERE application_id = ?", (app_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Application was not found.")
    application = json.loads(row["payload_json"])
    return {
        "application_id": application["id"],
        "scheme_name": application["scheme_name"],
        "status": application["status"],
        "applied_date": application["applied_date"],
        "officer_decision": application.get("officer_decision"),
        "officer_note": application.get("officer_decision_reason"),
        "dbt_status": application["dbt_status"],
    }


@app.post("/api/applications/{app_id}/decision")
async def decide_application(app_id: str, payload: OfficerDecisionRequest, request: Request):
    officer = _require_officer(request)
    action = payload.action.strip().upper()
    reason = payload.reason.strip()
    if action not in {"APPROVE", "REQUEST_CORRECTION", "REJECT"}:
        raise HTTPException(status_code=400, detail="Action must be APPROVE, REQUEST_CORRECTION, or REJECT.")
    if len(reason) < 5 or len(reason) > 1000:
        raise HTTPException(status_code=400, detail="Enter a review reason between 5 and 1000 characters.")

    status_by_action = {
        "APPROVE": "APPROVED_PENDING_POST_SELECTION",
        "REQUEST_CORRECTION": "DEFICIENCY_NOTICE_ISSUED",
        "REJECT": "REJECTED_BY_OFFICER",
    }
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with _db_connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload_json FROM applications WHERE application_id = ?", (app_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Application was not found.")
            application = json.loads(row["payload_json"])
            if application.get("status") != "PENDING_OFFICER_REVIEW":
                raise HTTPException(status_code=409, detail="This application is no longer awaiting its first officer decision.")
            application["status"] = status_by_action[action]
            application["officer_decision"] = action
            application["officer_decision_reason"] = reason
            application["officer_name"] = officer["full_name"]
            application["officer_decided_at"] = timestamp
            # An officer decision is not a selection-list finalization or a payment instruction.
            application["dbt_status"] = "NOT_INITIATED"
            connection.execute(
                "UPDATE applications SET payload_json = ?, status = ?, updated_at = ? WHERE application_id = ?",
                (json.dumps(application, ensure_ascii=False), application["status"], timestamp, app_id),
            )
            connection.execute(
                "INSERT INTO application_events(application_id, officer_user_id, officer_email, action, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (app_id, officer["user_id"], officer["email"], action, reason, timestamp),
            )
    except sqlite3.Error:
        raise HTTPException(status_code=500, detail="Could not save the officer decision.")
    return {"success": True, "application": application, "payment_initiated": False}

@app.post("/api/approve/{app_id}")
async def approve_application(app_id: str):
    raise HTTPException(status_code=410, detail="Use the authenticated officer decision workflow. No payment is initiated by this prototype.")

@app.get("/api/sample-docs/{doc_name}")
async def get_sample_doc(doc_name: str):
    """Allows 1-click loading of sample genuine/fake documents for live testing"""
    if Path(doc_name).name != doc_name or doc_name in {".", ".."}:
        raise HTTPException(status_code=404, detail="Sample doc not found")
    doc_file = (SAMPLE_DIR / doc_name).resolve()
    if SAMPLE_DIR.resolve() not in doc_file.parents:
        raise HTTPException(status_code=404, detail="Sample doc not found")
    if not doc_file.exists():
        raise HTTPException(status_code=404, detail="Sample doc not found")
    from fastapi.responses import FileResponse
    return FileResponse(doc_file, media_type="image/jpeg")

# --- ENTERPRISE PRODUCTION ROADMAP API ENDPOINTS (SIH26239) ---

@app.get("/api/rules/all")
async def get_all_scheme_rules():
    """Returns dynamic scheme parameters configured by MoTA Ministry Admins"""
    return rule_engine.scheme_rules

@app.post("/api/rules/evaluate")
async def evaluate_scheme_rule(payload: dict):
    """Evaluates applicant profile dynamically using AST Rule Engine"""
    scheme_code = payload.get("scheme_code", "PMS-ST")
    return rule_engine.evaluate_applicant(scheme_code, payload)

@app.post("/api/merit/allocate")
async def run_merit_allocation(payload: dict):
    """Do not publish a merit list until approved scheme-specific criteria are configured."""
    raise HTTPException(
        status_code=503,
        detail="Official scheme-specific selection criteria are not configured. No merit list was generated.",
    )

@app.post("/api/deficiency/trigger")
async def trigger_deficiency_notice(payload: dict):
    """Deficiency notices require an authenticated officer and a configured delivery service."""
    raise HTTPException(
        status_code=503,
        detail="Officer authentication and notification delivery are not configured. No notice was sent.",
    )

@app.get("/api/fellowship/all")
async def get_all_fellowships():
    """Fellowship records remain private until officer authentication is configured."""
    raise HTTPException(status_code=503, detail="Officer authentication is not configured.")

@app.post("/api/fellowship/endorse/{fellow_id}")
async def endorse_fellowship_milestone(fellow_id: str, payload: dict):
    """Milestone endorsement is unavailable until supervisor authentication and payment controls exist."""
    raise HTTPException(
        status_code=503,
        detail="Supervisor authentication and stipend integration are not configured. No endorsement was recorded.",
    )

# --- BIOMETRIC VERIFICATION & DPDP AUDIT LEDGER (SIH26239 SEC 5 & 9) ---

@app.post("/api/biometrics/verify-face")
async def verify_biometrics_face(
    selfie: UploadFile = File(...),
    reference_aadhaar_photo: Optional[UploadFile] = File(None)
):
    """Biometric matching is disabled pending consent, safeguards, and authorized integration."""
    raise HTTPException(
        status_code=503,
        detail="Biometric matching is not enabled in this prototype. No face comparison was performed.",
    )

@app.post("/api/dpdp/mask-aadhaar")
async def mask_aadhaar_dpdp(payload: dict):
    """Masks an Aadhaar value for display; this endpoint does not certify compliance."""
    raw_aadhaar = str(payload.get("aadhaar_no", ""))
    masked = aadhaar_vault.mask_aadhaar(raw_aadhaar)
    return {
        "status": "MASKED_FOR_DISPLAY",
        "masked_aadhaar": masked,
        "note": "No UIDAI lookup, identity verification, deduplication, or legal compliance certification was performed."
    }

@app.get("/api/ledger/blocks")
async def get_audit_ledger_blocks():
    """Audit records remain private until officer authentication is configured."""
    raise HTTPException(status_code=503, detail="Officer authentication is not configured.")

@app.post("/api/ledger/record")
async def record_ledger_action(payload: dict):
    """Audit writes require an authenticated officer identity."""
    raise HTTPException(
        status_code=503,
        detail="Officer authentication is not configured. No audit action was recorded.",
    )

if __name__ == "__main__":
    print("Starting TribalSetu Server at http://localhost:8000")
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
