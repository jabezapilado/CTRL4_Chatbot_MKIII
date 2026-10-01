-- Run this file against an already-created database selected by the deployment
-- environment. The application runtime database name is CHATBOT_DB_NAME.

CREATE TABLE IF NOT EXISTS accounts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    student_number VARCHAR(20) NULL UNIQUE,
    staff_number VARCHAR(20) NULL UNIQUE,
    gender ENUM(
        'Male',
        'Female',
        'Prefer not to say',
        'Other'
    ) NULL,
    program VARCHAR(100) NULL,
    assigned_programs JSON NULL,
    office VARCHAR(255) NULL,
    support_statement TEXT NULL,
    consultation_rooms JSON NULL,
    consultation_schedules JSON NULL,
    appointment_slots JSON NULL,
    consultation_modes JSON NULL,
    role ENUM(
        'student',
        'staff',
        'admin'
    ) NOT NULL DEFAULT 'student',
    status ENUM(
        'active',
        'disabled'
    ) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL,
    INDEX idx_accounts_email (email),
    INDEX idx_accounts_role (role),
    INDEX idx_accounts_status (status)
);

CREATE TABLE IF NOT EXISTS inquiries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NULL,
    inquiry_type VARCHAR(100) NOT NULL,
    emotion_result VARCHAR(100) NOT NULL,
    escalated TINYINT(1) NOT NULL DEFAULT 0,
    appointment_recommended TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (account_id)
    REFERENCES accounts(id)
    ON DELETE SET NULL,
    INDEX idx_inquiries_account (account_id),
    INDEX idx_inquiries_created (created_at)
);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NULL,
    primary_concern VARCHAR(255) NOT NULL,
    conversation_type VARCHAR(100) NOT NULL,
    emotion_results VARCHAR(255) NOT NULL,
    flagged_status TINYINT(1) NOT NULL DEFAULT 0,
    appointment_recommendation VARCHAR(255) NOT NULL,
    recommendations TEXT NULL,
    suggested_intervention TEXT NULL,
    language_used VARCHAR(50) NOT NULL,
    total_messages INT NOT NULL,
    summary TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (account_id)
    REFERENCES accounts(id)
    ON DELETE SET NULL,
    INDEX idx_conversation_summaries_account (account_id),
    INDEX idx_conversation_summaries_flagged_status (flagged_status),
    INDEX idx_conversation_summaries_created (created_at)
);

-- Raw transcripts are retained only after a conversation is flagged for
-- authorized Guidance Office review. Routine conversations have no durable
-- transcript record.
CREATE TABLE IF NOT EXISTS flagged_conversation_transcripts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_summary_id INT NOT NULL UNIQUE,
    transcript_json MEDIUMTEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (conversation_summary_id)
    REFERENCES conversation_summaries(id)
    ON DELETE CASCADE,
    INDEX idx_flagged_transcripts_summary (conversation_summary_id)
);

CREATE TABLE IF NOT EXISTS escalations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NULL,
    summary_id INT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    escalation_reason VARCHAR(255) NULL,
    intervention_notes TEXT NULL,
    created_at DATETIME NOT NULL,
    resolved_at DATETIME NULL,
    reviewed_at DATETIME NULL,
    FOREIGN KEY (account_id)
    REFERENCES accounts(id)
    ON DELETE SET NULL,
    FOREIGN KEY (summary_id)
    REFERENCES conversation_summaries(id)
    ON DELETE SET NULL,
    INDEX idx_escalations_account (account_id),
    INDEX idx_escalations_summary (summary_id),
    INDEX idx_escalations_status (status)
);

CREATE TABLE IF NOT EXISTS case_notes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_summary_id INT NOT NULL,
    staff_account_id INT NOT NULL,
    note_text TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (conversation_summary_id)
    REFERENCES conversation_summaries(id)
    ON DELETE RESTRICT,
    FOREIGN KEY (staff_account_id)
    REFERENCES accounts(id)
    ON DELETE RESTRICT,
    INDEX idx_case_notes_summary_created (
        conversation_summary_id,
        created_at
    ),
    INDEX idx_case_notes_staff (staff_account_id)
);

CREATE TABLE IF NOT EXISTS referrals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_summary_id INT NOT NULL,
    staff_account_id INT NOT NULL,
    destination VARCHAR(100) NOT NULL,
    referral_reason TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (conversation_summary_id)
    REFERENCES conversation_summaries(id)
    ON DELETE RESTRICT,
    FOREIGN KEY (staff_account_id)
    REFERENCES accounts(id)
    ON DELETE RESTRICT,
    INDEX idx_referrals_summary_created (
        conversation_summary_id,
        created_at
    ),
    INDEX idx_referrals_status (status)
);

CREATE TABLE IF NOT EXISTS referral_status_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    referral_id INT NOT NULL,
    staff_account_id INT NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (referral_id)
    REFERENCES referrals(id)
    ON DELETE RESTRICT,
    FOREIGN KEY (staff_account_id)
    REFERENCES accounts(id)
    ON DELETE RESTRICT,
    INDEX idx_referral_status_history_referral_created (
        referral_id,
        created_at
    )
);

CREATE TABLE IF NOT EXISTS referral_notes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    referral_id INT NOT NULL,
    staff_account_id INT NOT NULL,
    note_text TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (referral_id)
    REFERENCES referrals(id)
    ON DELETE RESTRICT,
    FOREIGN KEY (staff_account_id)
    REFERENCES accounts(id)
    ON DELETE RESTRICT,
    INDEX idx_referral_notes_referral_created (
        referral_id,
        created_at
    )
);

CREATE TABLE IF NOT EXISTS interventions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_summary_id INT NOT NULL,
    staff_account_id INT NOT NULL,
    intervention_type VARCHAR(100) NOT NULL,
    objective TEXT NOT NULL,
    progress_status VARCHAR(50) NOT NULL DEFAULT 'planned',
    outcome TEXT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (conversation_summary_id)
    REFERENCES conversation_summaries(id)
    ON DELETE RESTRICT,
    FOREIGN KEY (staff_account_id)
    REFERENCES accounts(id)
    ON DELETE RESTRICT,
    INDEX idx_interventions_summary_created (
        conversation_summary_id,
        created_at
    ),
    INDEX idx_interventions_progress_status (progress_status)
);

CREATE TABLE IF NOT EXISTS intervention_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    intervention_id INT NOT NULL,
    staff_account_id INT NOT NULL,
    progress_status VARCHAR(50) NOT NULL,
    outcome TEXT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (intervention_id)
    REFERENCES interventions(id)
    ON DELETE RESTRICT,
    FOREIGN KEY (staff_account_id)
    REFERENCES accounts(id)
    ON DELETE RESTRICT,
    INDEX idx_intervention_history_intervention_created (
        intervention_id,
        created_at
    )
);

CREATE TABLE IF NOT EXISTS case_confidentiality (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_summary_id INT NOT NULL UNIQUE,
    staff_account_id INT NOT NULL,
    confidentiality_status VARCHAR(50) NOT NULL,
    confidentiality_reason TEXT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (conversation_summary_id)
    REFERENCES conversation_summaries(id)
    ON DELETE RESTRICT,
    FOREIGN KEY (staff_account_id)
    REFERENCES accounts(id)
    ON DELETE RESTRICT,
    INDEX idx_case_confidentiality_status (confidentiality_status)
);

CREATE TABLE IF NOT EXISTS case_confidentiality_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    case_confidentiality_id INT NOT NULL,
    staff_account_id INT NOT NULL,
    confidentiality_status VARCHAR(50) NOT NULL,
    confidentiality_reason TEXT NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (case_confidentiality_id)
    REFERENCES case_confidentiality(id)
    ON DELETE RESTRICT,
    FOREIGN KEY (staff_account_id)
    REFERENCES accounts(id)
    ON DELETE RESTRICT,
    INDEX idx_case_confidentiality_history_record_created (
        case_confidentiality_id,
        created_at
    )
);

CREATE TABLE IF NOT EXISTS appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NOT NULL,
    contact_number VARCHAR(20) NOT NULL,
    appointment_category VARCHAR(100) NOT NULL,
    appointment_mode VARCHAR(50) NOT NULL,
    preferred_date DATE NOT NULL,
    preferred_time_slot VARCHAR(20) NOT NULL,
    reason TEXT NOT NULL,
    status ENUM(
        'pending',
        'confirmed',
        'cancelled',
        'rejected',
        'completed'
    ) NOT NULL DEFAULT 'pending',
    counselor_notes TEXT NULL,
    appointment_source ENUM(
        'chatbot',
        'walk_in',
        'hotline',
        'messenger',
        'email',
        'staff_manual'
    ) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    FOREIGN KEY (account_id)
    REFERENCES accounts(id)
    ON DELETE RESTRICT,
    INDEX idx_appointments_account (account_id),
    INDEX idx_appointments_preferred_date (preferred_date),
    INDEX idx_appointments_status (status),
    INDEX idx_appointments_created (created_at)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    recipient_account_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(50) NOT NULL,
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (recipient_account_id)
    REFERENCES accounts(id)
    ON DELETE RESTRICT,
    INDEX idx_notifications_recipient_created (
        recipient_account_id,
        created_at
    )
);

-- Privacy-safe student feedback. Chat transcripts and raw AI reply text are
-- intentionally not stored in this table.
CREATE TABLE IF NOT EXISTS chatbot_feedback (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_id INT NULL,
    conversation_summary_id INT NULL,
    response_token_hash CHAR(64) NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL,
    comment VARCHAR(500) NULL,
    response_context VARCHAR(50) NULL,
    created_at DATETIME NOT NULL,
    FOREIGN KEY (account_id)
    REFERENCES accounts(id)
    ON DELETE SET NULL,
    FOREIGN KEY (conversation_summary_id)
    REFERENCES conversation_summaries(id)
    ON DELETE SET NULL,
    INDEX idx_chatbot_feedback_account_created (
        account_id,
        created_at
    ),
    INDEX idx_chatbot_feedback_summary (
        conversation_summary_id
    )
);

CREATE TABLE IF NOT EXISTS settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(100) NOT NULL UNIQUE,
    setting_value TEXT NOT NULL,
    updated_at DATETIME NOT NULL
);

-- Never store plaintext passwords.
-- All passwords must be generated using Werkzeug's
-- generate_password_hash() before insertion.
-- Self-service password changes replace accounts.password_hash only after
-- the authenticated account's current password has been verified.
-- Accounts can also be seeded through
-- backend/.env using scripts/setup_database.py.
