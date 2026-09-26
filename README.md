# 🛡️ TribalSetu — AI Scholarship & Fellowship Management System
> **Smart India Hackathon (SIH) 2026 | Problem Statement ID: 26239**  
> **Ministry of Tribal Affairs (MoTA), Government of India | Theme: Smart Education**

---

## 📌 Overview
**TribalSetu** is a prototype for scholarship application intake, document review signals, and officer workflow for tribal scholarship schemes. AI output is advisory; eligibility, selection, and payment remain separate human or authorized-system steps. Performance and fraud-reduction outcomes have not yet been measured.

---

## 🚀 Key Features
- **🔬 ELA image check:** Highlights image-compression differences for officer review; it cannot by itself prove document tampering.
- **📱 QR parsing:** Decodes available QR content. A certificate signature is not treated as valid until a trusted issuer key is configured.
- **📜 Article 342 directory:** Prototype reference data supports a preliminary community lookup; it does not replace official certificate verification.
- **🛡️ Aadhaar display masking:** The submission record stores a masked value. This prototype does not integrate with UIDAI or certify DPDP compliance.
- **💾 Local persistence:** SQLite stores application metadata, officer accounts, and review events for local demonstration.
- **🚦 Human-led workflow:** Applications enter officer review; AI signals do not auto-approve, auto-reject, or initiate a payment.

---

## 🌐 Live Demonstrations & Cloud Deployment

| Service | Link | Description |
| :--- | :--- | :--- |
| **GitHub Pages UI preview** | **[https://priyanshu7061748351.github.io/tribalsetu/](https://priyanshu7061748351.github.io/tribalsetu/)** | Static interface preview; backend screening and officer actions require the local FastAPI server. |
| **Static screening UI preview** | [https://priyanshu7061748351.github.io/tribalsetu/static/trial.html](https://priyanshu7061748351.github.io/tribalsetu/static/trial.html) | Shows the interface only; it does not verify documents with a government authority. |
| 📑 **SIH Master Plan** | [https://priyanshu7061748351.github.io/tribalsetu/static/TribalSetu_SIH2026_Master_Plan.html](https://priyanshu7061748351.github.io/tribalsetu/static/TribalSetu_SIH2026_Master_Plan.html) | Complete SIH 2026 Problem Statement and Execution Dossier. |
| 📊 **System Flowchart** | [https://priyanshu7061748351.github.io/tribalsetu/static/TribalSetu_Master_Flowchart_and_Deep_Dive.html](https://priyanshu7061748351.github.io/tribalsetu/static/TribalSetu_Master_Flowchart_and_Deep_Dive.html) | End-to-end interactive architecture flowchart. |

---

## 🛠️ Quick Start Guide

## What the Local Prototype Can and Cannot Do

| It can do locally | It cannot do in this prototype |
| --- | --- |
| Read an uploaded PDF (up to the first five pages) or supported image and show best-effort OCR text candidates. | Prove a certificate genuine/fake, validate its issuing authority or digital signature, or decide ST/BC scheme eligibility. |
| Report QR presence and, for JPEG images, a limited compression/ELA signal. Both are review clues only. | Verify a QR signature, query Bihar RTPS automatically, or connect to MoTA, DigiLocker, UIDAI, NPCI, PFMS, a bank, or DBT. The Bihar link is a manual handoff. |
| Submit application metadata to the local SQLite demo store after the local review-token flow and show a tracking status. | Make an official selection, approve/reject an applicant automatically, store uploaded source documents, send SMS/WhatsApp alerts, or transfer money. |
| Use the browser's speech input/output with a small set of built-in help replies. | Act as a live generative-AI assistant or provide an official eligibility decision. |

OCR may miss or misread text. A missing OCR field means the app did not extract it; it is not evidence that a certificate is wrong. Every screening outcome remains for human review.

### 1. Prerequisites
- Python 3.10+ installed
- Git installed

### 2. Clone & Install Dependencies
```bash
git clone https://github.com/priyanshu7061748351/tribalsetu.git
cd tribalsetu

# Install dependencies
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Start Local Server
On Windows, double-click **`Start TribalSetu.bat`** in the project folder. It starts the local API in a visible console and opens the browser. It uses port 8000 by default, or 8001/8002 if an older process is using a port. Keep the server console open while using the app; close it or press Ctrl+C there to stop the server. If this app is already running, the launcher opens it without starting a second copy.

**Do not open `index.html` directly.** A `file:///.../index.html` page cannot call this app's local API, so document screening, application saving, and officer queue requests will not work. Use the browser tab opened by the launcher.

Alternatively, after installing dependencies, start it in PowerShell with:

```powershell
.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```

### 4. Open in Browser
- **🚀 4-in-1 Document Verification Trial Demo:** [http://127.0.0.1:8000/trial](http://127.0.0.1:8000/trial)
- **🏠 Main Student & Officer Portal:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **📖 API Documentation (Swagger):** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

For a separate officer-authentication setup, run these commands in one PowerShell window instead of using the launcher. This keeps the setup token private and gives sessions a persistent key:

```powershell
function New-Secret { $bytes = New-Object byte[] 48; $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create(); $rng.GetBytes($bytes); [Convert]::ToBase64String($bytes) }
$env:TRIBALSETU_BOOTSTRAP_TOKEN = New-Secret
$env:TRIBALSETU_SESSION_SECRET = New-Secret
Write-Host "One-time officer setup token: $env:TRIBALSETU_BOOTSTRAP_TOKEN"
.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```

The local server stores submitted applications, officer accounts, and officer review events in `data/tribalsetu.sqlite3`. Open the Officer Queue and create the first officer with the setup token configured above. Officer passwords are stored as salted PBKDF2 hashes; sessions use an HTTP-only cookie. Keep both secrets private. If the process starts without `TRIBALSETU_SESSION_SECRET`, it uses a temporary key and all officer sessions end when the server restarts.

Uploaded source documents are analyzed and then discarded in this milestone; the officer queue retains only application metadata and review signals. The dashboard warns against using its actions as official decisions until a safeguarded document store and reviewer viewer are implemented. An officer's **Approve for next stage** action records a prototype review decision only. It does not select a scholarship recipient or initiate a DBT payment. SQLite on a local filesystem is not a production deployment store. Before hosting, migrate to managed PostgreSQL and protected document storage, configure persistent storage and secrets, and add account provisioning, rate limits, and recovery controls. The static GitHub Pages site cannot submit applications or use the local officer queue.

---

## 📂 Project Architecture
```
tribalsetu_app/
├── server.py               # FastAPI backend with trial & verification APIs
├── requirements.txt        # Python dependency manifest
├── test_pipeline.py        # Automated test suite
│
├── ai_engine/              # 🧠 AI Forensic & Verification Modules
│   ├── pipeline.py         # Master orchestrator chaining all 8 stages
│   ├── preprocessor.py     # OpenCV perspective transform & deskewing
│   ├── ela_tamper.py       # ELA JPEG compression variance forensics
│   ├── qr_engine.py        # Dual-engine QR scanner (zxing-cpp + OpenCV)
│   ├── ocr_engine.py       # Dual-language regex key-value extraction
│   ├── st_gazette.py       # Constitution Article 342 ST database
│   ├── identity_matcher.py # Fuzzy string token-sort Levenshtein matcher
│   ├── dbt_checker.py      # NPCI APB Direct Benefit Transfer simulator
│   └── trust_scorer.py     # Composite scoring & Green/Yellow/Red triage
│
└── static/                 # 🌐 Responsive Web Interfaces
    ├── index.html          # Student & Officer Dashboard
    ├── trial.html          # Live 4-in-1 Document Verification Demo
    ├── app.js              # Frontend client application logic
    └── styles.css          # Dark glassmorphism stylesheet
```

---

## 🧪 Run Automated Tests
```bash
python test_pipeline.py
```
*(All 3 tests: Genuine ST Certificate, Tampered Fake Document, and Offline Fallback pass automatically)*

---

## 👥 Authors
Developed for Smart India Hackathon (SIH) 2026.
