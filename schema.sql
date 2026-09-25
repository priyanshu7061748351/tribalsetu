-- ====================================================================
-- TRIBALSETU ENTERPRISE RELATIONAL SCHEMA (POSTGRESQL 16)
-- Conforms to Section 10 of SIH 2026 Problem Statement ID: 26239
-- Ministry of Tribal Affairs (MoTA), Government of India
-- ====================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. USERS & ROLES TABLE
CREATE TYPE user_role AS ENUM (
    'STUDENT', 
    'INO',          -- Institute Nodal Officer (School / College Principal)
    'DWO',          -- District Welfare Officer
    'SNO',          -- State Nodal Officer
    'MOTA_ADMIN',    -- Central Ministry Administrator
    'SUPERVISOR'    -- Research Supervisor (Ph.D. / M.Phil Guide)
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(15) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role user_role NOT NULL,
    aadhaar_hash CHAR(64) UNIQUE NOT NULL, -- SHA-256 Salted Hash (Zero Knowledge DPDP Act 2023)
    masked_aadhaar VARCHAR(14) NOT NULL,   -- 'XXXX-XXXX-1234'
    full_name VARCHAR(255) NOT NULL,
    state VARCHAR(100),
    district VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. SCHEMES MASTER TABLE
CREATE TABLE IF NOT EXISTS schemes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scheme_code VARCHAR(50) UNIQUE NOT NULL, -- 'PMS-ST', 'NFST', 'NOS', 'TOPCLASS-ST'
    name VARCHAR(255) NOT NULL,
    ministry VARCHAR(255) DEFAULT 'Ministry of Tribal Affairs',
    academic_year VARCHAR(20) NOT NULL,
    max_annual_income NUMERIC(12, 2) NOT NULL, -- e.g. 250000.00 for PMS-ST
    st_category_mandatory BOOLEAN DEFAULT TRUE,
    total_slots INT, -- NULL for entitlement schemes (PMS), 750 for NFST, 20 for NOS
    funding_ratio_centre_state VARCHAR(20) DEFAULT '75:25',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. APPLICATIONS TABLE
CREATE TYPE triage_decision AS ENUM ('GREEN', 'YELLOW', 'RED');
CREATE TYPE application_status AS ENUM (
    'DRAFT', 
    'SUBMITTED', 
    'AUTO_APPROVED', 
    'UNDER_DWO_REVIEW', 
    'DEFICIENCY_NOTICE_ISSUED',
    'APPROVED', 
    'REJECTED', 
    'DISBURSED'
);

CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_number VARCHAR(50) UNIQUE NOT NULL, -- 'APP-2026-XXXXX'
    student_id UUID REFERENCES users(id) ON DELETE CASCADE,
    scheme_id UUID REFERENCES schemes(id),
    institute_name VARCHAR(255) NOT NULL,
    course_name VARCHAR(255) NOT NULL,
    annual_income NUMERIC(12, 2) NOT NULL,
    claimed_caste VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    district VARCHAR(100) NOT NULL,
    
    -- AI Forensic 8-Stage Metrics
    trust_score NUMERIC(5, 2) NOT NULL, -- 0.00 to 100.00
    triage_band triage_decision NOT NULL,
    status application_status DEFAULT 'SUBMITTED',
    
    -- Forensic Sub-Scores
    qr_integrity_score NUMERIC(5, 2) DEFAULT 0.0,
    ela_tamper_score NUMERIC(5, 2) DEFAULT 0.0,
    identity_match_score NUMERIC(5, 2) DEFAULT 0.0,
    gazette_compliance_score NUMERIC(5, 2) DEFAULT 0.0,
    dbt_readiness_score NUMERIC(5, 2) DEFAULT 0.0,
    biometric_similarity_score NUMERIC(5, 2) DEFAULT 0.0,
    
    -- Verification Artifacts & JSON Audit Trail
    audit_trail JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_dbt_ready BOOLEAN DEFAULT FALSE,
    assigned_officer_id UUID REFERENCES users(id),
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. VERIFIED DOCUMENTS TABLE
CREATE TYPE doc_type AS ENUM (
    'AADHAAR', 
    'CASTE_CERTIFICATE', 
    'INCOME_CERTIFICATE', 
    'DOMICILE', 
    'MARKSHEET',
    'SELFIE_LIVENESS'
);

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    application_id UUID REFERENCES applications(id) ON DELETE CASCADE,
    document_type doc_type NOT NULL,
    s3_storage_uri VARCHAR(512) NOT NULL,
    s3_heatmap_uri VARCHAR(512),
    is_qr_present BOOLEAN DEFAULT FALSE,
    qr_payload TEXT,
    ocr_extracted_fields JSONB DEFAULT '{}'::jsonb,
    is_tampered BOOLEAN DEFAULT FALSE,
    tamper_confidence NUMERIC(5, 2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. AUDIT & DISBURSEMENT LEDGER (Tamper-Proof Blockchain-Style Chained Hash)
CREATE TABLE IF NOT EXISTS disbursement_ledger (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    block_index BIGSERIAL UNIQUE,
    application_id UUID REFERENCES applications(id),
    sanctioned_amount NUMERIC(12, 2) NOT NULL,
    pfms_transaction_id VARCHAR(100) UNIQUE,
    dbt_account_last4 CHAR(4) NOT NULL,
    officer_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL, -- 'AUTO_APPROVED_GREEN_QUEUE', 'PFMS_BATCH_DISBURSED'
    disbursement_status VARCHAR(50) DEFAULT 'PROCESSING',
    previous_block_hash CHAR(64) NOT NULL,
    current_block_hash CHAR(64) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. RESEARCH FELLOWSHIPS TABLE (NFST M.Phil / Ph.D. Lifecycle)
CREATE TABLE IF NOT EXISTS research_fellowships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fellow_id VARCHAR(50) UNIQUE NOT NULL, -- 'NFST-2026-PHD-041'
    scholar_name VARCHAR(255) NOT NULL,
    caste VARCHAR(100) NOT NULL,
    university VARCHAR(255) NOT NULL,
    research_topic TEXT NOT NULL,
    supervisor_id UUID REFERENCES users(id),
    supervisor_name VARCHAR(255) NOT NULL,
    monthly_stipend NUMERIC(10, 2) DEFAULT 38000.00,
    hra_amount NUMERIC(10, 2) DEFAULT 6080.00,
    current_milestone VARCHAR(100) NOT NULL,
    progress_status VARCHAR(50) DEFAULT 'SATISFACTORY',
    supervisor_endorsed BOOLEAN DEFAULT FALSE,
    stipend_disbursement_status VARCHAR(50) DEFAULT 'PENDING_ENDORSEMENT',
    last_endorsed_at TIMESTAMP WITH TIME ZONE
);

-- 7. PERFORMANCE INDEXES
CREATE INDEX IF NOT EXISTS idx_apps_status_triage ON applications(status, triage_band);
CREATE INDEX IF NOT EXISTS idx_apps_student ON applications(student_id);
CREATE INDEX IF NOT EXISTS idx_apps_scheme ON applications(scheme_id);
CREATE INDEX IF NOT EXISTS idx_users_aadhaar ON users(aadhaar_hash);
CREATE INDEX IF NOT EXISTS idx_ledger_block ON disbursement_ledger(block_index, current_block_hash);
