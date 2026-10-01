# Changelog

All notable changes to the CTRL4 Chatbot project are documented in this file.

The format follows the principles of **Keep a Changelog**.

---

## [Unreleased]

### Changed

- Consolidated crisis escalation messaging into the chatbot response so the
  student sees one clear reply that confirms counselor referral and follow-up;
  the duplicate escalation banner is no longer rendered separately.
- Added accessible tab semantics to the Privacy, Referrals, and Interventions
  Case Records controls, including selected-state and panel relationships while
  preserving Staff Action as the final independent card.
- Reworked the Case Details overview so the AI Summary appears lower in the
  main case profile and the AI Recommendation uses a clearer highlighted callout
  for immediate staff follow-up.
- Simplified the Staff Action card and moved the **Mark Reviewed** control to
  the bottom-right below its Guidance Office notice.
- Kept Staff Actions independent in the right-side panel, reduced the main
  Case Details navigation to Overview and Conversation, and made Privacy,
  Referrals, and Interventions the independent Case Records controls.
- Replaced the long Case Records management stack with compact Actions,
  Privacy, Referrals, and Interventions controls so staff work with one form at
  a time while Counselor Notes remains at the top-right.
- Organized staff Case Details into Overview, Conversation, and Case Records
  tabs. Counselor Notes and Staff Actions remain at the top-right for every
  tab, while transcripts and other restricted records stay staff-only.
- Added staff-only case-priority indicators and filters. Critical immediate
  safety escalations, high-priority warning-sign reviews, medium active
  conversations, and low routine summaries are derived from existing case
  state; Critical staff notifications are visually distinguished and state the
  required immediate review.
- Moved the Counselor Notes card to the top of the Case Details right-side
  staff panel so counselors can record follow-up, referral, or action notes
  before taking other case actions.
- Removed the student-facing Case Status page and its API. Persisted case
  statuses are now available only through authorized Guidance staff case
  workflows.
- Flagged conversations now retain their server-owned transcript for
  authorized, program-scoped Guidance staff review. Routine conversation
  transcripts remain temporary, and students and administrators cannot access
  retained flagged-case transcripts.

### Added

- Added an administrator-only student-account CSV import workflow for Guidance
  Office onboarding. It accepts the published UTF-8 template with only
  `full_name`, `email`, `gender`, and `program`; validates all rows and active
  programs before creation; allocates student numbers server-side; and provides
  a one-time credentials CSV download. Uploads cannot create staff or
  administrator accounts or set passwords, and temporary passwords are neither
  logged nor returned by later account-listing requests.

- Added client-side pagination to the staff Inbox and Flagged Cases (7 records
  per page), Chatbot Feedback, dashboard analytics and reports (10 records per
  page), and administrator account and program-management tables (8 records
  per page). Dashboard panels grow with their paginated records and use normal
  page scrolling on short screens instead of a nested vertical table scrollbar.
  Controls appear only when a table exceeds one page; filtering, sorting, and
  applying a new analytics range return that table to its first page without
  changing the authorized server data.

- Added a VPS-owned student chat inactivity finalizer. After 20 minutes without
  a completed chat exchange, it finalizes the existing active conversation via
  the normal summary, safety, and Inbox workflow, then invalidates that
  student lease. This also handles closed browsers, which cannot run the
  client-side finalization code.

- Added an administrator-only **Reset password** action for student accounts.
  It uses a dedicated confirmation form, stores only a newly generated password
  hash, and never exposes the previous password.

- Added an opt-in, survey-only student self-registration flow. It is disabled
  by default and requires both a VPS-only enable switch and private survey
  code. It creates only student accounts, generates student numbers
  server-side, accepts only active programs and `@student.hau.edu.ph` emails,
  and retains the normal sign-in and Terms acknowledgement flow.
- Student-number allocation now retries a database collision during concurrent
  registrations, so survey participants registering at the same time do not
  lose their account creation request because they were assigned the same next
  number.

- Added a local SSH-tunnel helper for secure production database UI access.
  It forwards a Mac or workstation-local port to the VPS-local MySQL listener
  without exposing MySQL or a database administration UI to the internet.
- Added a separate local helper for optional phpMyAdmin access through an SSH
  tunnel, with no public phpMyAdmin route, firewall rule, or stored database
  credential.
- Added a local SSH-tunnel helper for the optional Cockpit VPS administration
  UI, keeping its system-administration port private to the VPS.
- Added a student-only single-active-device safeguard. When a student confirms
  a sign-in on Device B, CTRL4 first finalizes Device A through the existing
  conversation, safety, summary, and staff-Inbox workflow, then issues Device
  B a fresh session and Terms acknowledgement. Device A follows the normal
  signed-out login flow on its next request; staff and administrator
  multi-device sessions are unchanged. The Device B confirmation now uses an
  in-page cross-browser card with explicit **Cancel** and **Sign out other
  device and continue** actions. An open Device A chat now detects replacement
  within 15 seconds (or when brought back to the foreground), shows a centered
  session-ended notice, and then returns to the normal sign-in flow.
- Added turn-based student chat controls: the message field, Send button, and
  quick replies are unavailable while a response is pending.
- Added a short typing state for ordinary chatbot replies. The Send control
  and quick replies remain unavailable during that turn. Safety escalation
  replies bypass the artificial delay and remain immediate.
- Added notification navigation: opening an unread item marks it read and
  routes staff high-risk alerts to Flagged Cases, staff appointment alerts to
  Appointment Requests, and student appointment alerts to My Appointments.
- Added separate AI-professional and web-professional qualitative evaluation
  templates, linked from the documentation index.
- Added counselor-approved staff-review flags for first-person reports of
  feeling empty, feeling depressed, hopelessness, worthlessness, social
  withdrawal, giving away important belongings, past abuse disclosures, and
  self-diagnosis requests. These retain an appropriate supportive or
  diagnosis-boundary response while immediately creating a pending Guidance
  Office review case. They do not create a high-risk notification unless
  explicit immediate danger is also detected.

### Changed

- Removed the horizontal row-shift animation from dashboard tables. Hovering a
  row now uses a stable background highlight, preventing a transient horizontal
  scrollbar and table-width adjustment on paginated desktop views.

- Updated the staff Inbox, Flagged Cases, and Chatbot Feedback layouts so their
  primary table panels use the available viewport height and place pagination
  controls at the panel bottom. Compact viewports retain normal page scrolling
  when stacked records need more vertical space.

- Reduced the simulated typing state for ordinary chatbot replies from
  1.2–2.2 seconds to 0.3–0.7 seconds. Safety escalation replies continue to
  bypass the simulated delay entirely.

- Fixed the survey-registration page so its account-created notice is hidden
  until the current browser successfully submits the form, and the completed
  form then consistently disappears in Safari, Chrome, Firefox, and other
  browsers.
- Gemini responses that explicitly reach the configured output-token limit,
  consume the complete output-token budget despite a normal provider finish
  result, or visibly end mid-sentence now receive one concise-completion retry.
  The retry has a response-only 1,536-token ceiling and a 160-word completion
  contract. CTRL4 never displays the original incomplete candidate; if the
  retry is also incomplete, it safely reports a generation failure instead of
  a cut-off reply.
- Refined operational Guidance Office question recognition so a general or
  hypothetical reference to a counselor cannot be mistaken for an office
  location request. Those questions continue to the normal safe response path.

- Improved active-chat continuity without creating a durable transcript. CTRL4
  now retains up to 50 recent exchanges for the authenticated active session
  (previously 12), while keeping the same maximum text budget. The configured
  Gemini temperature and output-token limit are now passed to Gemini for each
  generation; the token setting limits reply length, not conversation memory.
- Centered the Administrator account-creation and program-creation dialogs in
  the viewport while retaining their existing responsive scrolling behavior.
- Stabilized the student chat on mobile and tablet browsers: keyboard viewport
  updates apply immediately so the shell does not visibly lag behind iOS
  Safari's keyboard pan. The chat viewport avoids accidental page/double-tap
  zoom, and the shell compensates for iOS viewport-pan offsets while opening or
  closing the keyboard. The header remains anchored while composing. Tapping
  the non-interactive conversation area now dismisses the mobile software
  keyboard without blocking a scroll gesture, and the composer provides
  browser-safe plain-text autocomplete hints. These presentation-only changes
  do not alter chat, safety, or session behavior.
- Fixed the in-app notification popover in the student chat and staff header.
  It now renders above headers that clip decorative overflow, remains anchored
  to the bell, and preserves its existing recipient-scoped loading, read, and
  destination behavior.
- Improved staff dashboard responsiveness without changing any case workflow:
  independent dashboard data loads now run in parallel, opening a flagged case
  loads its protected supporting records concurrently, and marking a case
  reviewed refreshes only the affected Inbox and Flagged Cases lists.
- Fixed the Case Details action state after navigating from a routine Inbox
  item to a pending flagged case: **Mark as Reviewed** is now visible and
  available to authorized staff whenever that case is still pending.
- Updated the student chatbot avatar to a fox and refined the compact mobile
  chat layout. The header, message bubbles, Terms dialog, and message composer
  now remain within small phone viewports and respect iPhone safe areas.
- Updated the student notification guide to describe opening a notification as
  the read action and its appointment destination.
- Improved the Guidance Office response-playbook review template spacing for
  easier review and completion.
- Retained only the approved `ai_engine/models/english/latest` tokenizer and
  configuration release in source control. Legacy model releases and training
  checkpoints are now local archives, and the tokenizer loader uses the same
  approved `latest` release as the runtime model loader.
- Updated the production schema reference with per-counselor appointment
  preferences and the privacy-safe chatbot-feedback table.
- Restricted production database creation to the explicit initialization path,
  allowing the deployed application account to remain database-scoped.

### Verified

- Passed focused frontend, chatbot-quality, conversation-finalization,
  notification, CSRF/CORS, integration, and documentation contracts after the
  chat and notification changes.

### Notes

- Production uses the documented persistent-VPS deployment topology. The
  current filesystem session, active-chat, model-artifact, and RAG runtime
  design require persistent host storage and controlled operational assets.
- Generated RAG index artifacts, PDFs, local reference scans, backups, and
  environment files remain outside this source-control update.
- Legacy model archives remain outside the repository. The controlled
  `model.safetensors` runtime artifact is provisioned separately.

---

## [1.0.7] - MK III Safety, Staff Workflow, and Release Update — August 2026

### Added

- Added immediate staff Inbox visibility for active student conversations,
  using a single in-progress summary record that is updated when the
  conversation is finalized rather than duplicated.
- Added per-reply student chatbot feedback, privacy-safe counselor feedback
  review, feedback filters, reply-context filtering, and review-signal cards.
- Added pending and reviewed views for flagged cases, with the sidebar count
  limited to cases that still require staff action.
- Added clearer Global Office Settings and My Staff Settings views. Counselor
  availability, selectable appointment start times, and consultation modes are
  now explicitly per-staff; shared office information, booking rules, and FAQ
  content remain global.
- Added a student-only Terms and Conditions acknowledgement before chatbot
  access. Acceptance is required for each server-side session; declining ends
  the session.

### Changed

- Made safety detection and escalation authoritative before duplicate-response
  prevention, generic fallbacks, and ordinary response variation. Crisis,
  self-harm, harm-to-others, and escalation replies now bypass the repetition
  guard.
- Updated the staff Inbox, Flagged Cases, Feedback, notifications, settings,
  and navigation interfaces for consistent filtering, sorting, status display,
  responsive layout, and return-to-Inbox navigation.
- Centered the student Terms and Conditions dialog and refined chatbot
  feedback controls while preserving the CTRL4 color palette.
- Updated the release, deployment, and user documentation for the v1.0.7
  implementation, privacy-safe staff views, English-focused emotion-model
  limitation for Filipino/Taglish input, and private Tailscale demonstration
  procedure.

### Verified

- Verified normal student chat, per-reply feedback, appointment routing,
  counselor-scoped Inbox visibility, staff feedback access, and program-scoped
  privacy boundaries using the supported student and staff workflows.
- Verified a crisis message receives the immediate safety response and is
  surfaced as a pending flagged case for the routed counselor.
- Passed the focused release regression suite covering chatbot quality,
  feedback, settings, conversation finalization, staff/admin boundaries,
  frontend contracts, and CSRF/CORS security.

### Notes

- v1.0.7 is suitable for a controlled release or demonstration once the
  Guidance Office has approved the emergency contacts, escalation wording, and
  local response procedure.
- Generated RAG artifacts, `.env` files, SQL backups, and the deferred
  hardening patch remain outside the release commit.

---

## [1.0.6] - MK III Final Release — August 2026

### Added

- Added deterministic crisis-response coverage for explicit self-harm, weapon,
  jumping, imminent-unsafety, and harm-to-others wording so these messages
  receive the safety response before any LLM or duplicate-response fallback.
- Added final release documentation alignment across README, architecture
  references, deployment guides, and user documentation.
- Added final environment configuration reference through the updated
  `.env.example`.
- Added finalized release references and repository documentation consistency
  for CTRL4 Chatbot MK III.

### Changed

- Finalized the CTRL4 Chatbot MK III release state after documentation review,
  repository cleanup, and release validation.
- Updated release references from v1.0.5 to v1.0.6 across project documentation.
- Updated final deployment and configuration references based on the validated
  local development environment.
- Preserved unvalidated startup hardening changes as archival material and
  excluded them from the final released system.

### Verified

- Completed final regression validation for authentication, security,
  conversation finalization, documentation contracts, and system workflows.
- Verified release documentation consistency with the implemented MK III
  architecture.
- Verified GitHub release tagging and repository state for the final release.

### Notes

- This release represents the finalized CTRL4 Chatbot MK III implementation.
- Historical MK I and MK II changes remain preserved in previous changelog
  entries.

---

## [3.0.0] - CTRL4 Chatbot MK III v1.0 — August 2026

### Added

- Completed the authenticated chatbot and internal Conversation Intelligence
  pipeline for intent, emotion, topic, metadata, language, summaries, safety,
  retrieval, prompting, and escalation handling.
- Completed Appointment Management with dynamic program-based counselor routing,
  normalized start-time conflict handling, schedule and availability checks,
  canonical lifecycle management, student replacement rescheduling, and
  persistent in-app notifications.
- Added Guidance case-management workflows: flagged cases, dedicated counselor
  notes, referrals and histories, interventions and histories, confidential
  case handling, and the privacy-projected student case-status dashboard.
- Added staff aggregate analytics for appointments, chatbot activity, counselor
  workload, and flagged cases, plus Reports & client-side CSV export.

### Changed

- Standardized completed application workflows around the implemented Route →
  Service → Database architecture, server-side sessions, role boundaries, and
  established response envelopes.
- Added atomic database-backed active-slot persistence for appointment conflict
  protection without introducing counselor ownership or duration assumptions.
- Normalized current implementation branding, release documentation, API
  reference, installation/deployment guidance, and student, staff, and
  administrator user guides to CTRL4 Chatbot MK III.

### Verified

- Completed System Integration Testing, Security & Privacy Testing, and
  Performance & Reliability Testing infrastructure and regression coverage.
- Completed Deployment Preparation, current-reference documentation review,
  final release audit, and repository cleanup of confirmed legacy artifacts.
- Preserved historical MK II changelog history, roadmap material, and model or
  training provenance as archival records.

---

## [2.0.0] - MK II Stable — July 2026

### Added

#### Artificial Intelligence

- Modular AI architecture
- AIService orchestration layer
- LLMService abstraction
- Provider-based LLM architecture
- GeminiProvider
- OllamaProvider
- BaseProvider interface
- Retrieval-Augmented Generation (RAG)
- PromptBuilder service
- Emotion-aware prompting
- Language-aware prompting
- Dynamic system prompts
- Conversation context support
- AI pipeline performance logging

#### Natural Language Processing

- English Emotion Recognition Model (EERM)
- Emotion detection
- Language detection
- Safety validation
- Crisis detection
- Emotion confidence scoring
- Negative sentiment detection
- English language support
- Filipino language detection
- Taglish language detection

#### Student Features

- AI Guidance Chat
- Guidance Office information retrieval
- Appointment booking
- Conversation export
- Responsive chatbot interface

#### Staff Features

- Guidance dashboard
- Appointment management
- Student concern monitoring

#### Backend

- Modular service architecture
- Environment-based configuration
- Provider switching
- Centralized AI initialization
- Performance monitoring
- Improved error handling

#### Documentation

- Complete project README
- Project Architecture documentation
- Dataset Documentation
- Preprocessing Pipeline documentation
- Model Architecture documentation
- API Integration guide
- Deployment Guide
- Future Work roadmap
- Design Decisions documentation
- CTRL4 Bible
- English model documentation
- Filipino model roadmap
- CHANGELOG

---

### Changed

#### Artificial Intelligence

- Introduced provider-based LLM architecture.
- Redesigned the AI pipeline into modular services.
- Moved prompt construction to the PromptBuilder service.
- Integrated Retrieval-Augmented Generation (RAG) into response generation.
- Performed safety validation before LLM generation.
- Incorporated emotion detection into prompt engineering.
- Integrated language detection into response generation.

#### Frontend

- Updated branding from Holy Angel University to the School of Computing.
- Updated the user interface color palette from red to orange.
- Improved chatbot interface.
- Improved dashboard layout.
- Improved appointment management interface.

#### Backend

- Improved project folder organization.
- Separated AI services from LLM provider implementations.
- Centralized application configuration.
- Improved AI service initialization and dependency management.

---

### Fixed

- HTTP 500 errors during AI generation failures.
- Duplicate AI pipeline performance logs.
- Gemini provider initialization issues.
- Ollama provider integration issues.
- Prompt generation consistency.
- Exception handling across AI services.
- Response generation reliability.
- AI pipeline logging output.

---

### Removed

- Rule-based chatbot responses.
- Legacy chatbot response handling.
- Prototype AI orchestration logic.
- Hardcoded chatbot responses.
- Deprecated MK I placeholder comments.
- Legacy Holy Angel University branding assets.
- Chat takeover workflow from MK I.

---

## [1.0.0] - MK I — June 2026

Initial prototype release.

### Added

#### Artificial Intelligence

- Basic chatbot implementation

#### Student Features

- Student authentication
- Chat interface
- Guidance Office FAQ
- Appointment prototype

#### Staff Features

- Guidance dashboard
- Chat takeover
- Student concern monitoring

#### Frontend

- Holy Angel University branding
- Red user interface theme
- Initial dashboard

#### Backend

- Flask backend
- Basic authentication
- Initial chatbot routing
