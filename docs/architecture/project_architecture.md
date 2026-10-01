# CTRL4 Chatbot MK III — Current Project Architecture

> **Current reference.** This document describes the implemented system in the
> current CTRL4 Chatbot MK III release line. Start at the [documentation
> index](../README.md). For implementation constraints and frozen decisions,
> read [Project Context](project_context.md). Documents in
> [roadmap/](../roadmap/) are historical planning artifacts.

## Purpose and major domains

CTRL4 is an authenticated Guidance Office support system for Holy Angel
University. Its implemented domains are account management, appointments,
in-app notifications, chatbot conversations and finalization, flagged-case
management, counselor notes, referrals, interventions, confidentiality, and
staff analytics/reports.

The stack is Flask, MySQL/MariaDB, server-side CacheLib sessions, a JavaScript
frontend, FAISS-backed retrieval, and Gemini or Ollama through the LLM provider
abstraction.

## System ownership

```text
Frontend → Route → Service → Database
```

| Layer | Owns | Must not own |
| --- | --- | --- |
| Frontend | Presentation, safe rendering, interaction, advisory checks | Authorization or authoritative business rules |
| Route | HTTP parsing, RBAC, Flask sessions, boundary logging, status codes, response serialization | Persistence orchestration or domain policy |
| Service | Validation, workflows, privacy projections, analytics aggregation, appointment rules, notifications, conversation and AI orchestration | Flask `session`, `request`, blueprints, or JSON serialization |
| Database | Parameterized retrieval/persistence, migrations, transactions, advisory locking, integrity safeguards | API behavior, counselor routing, or booking policy |

`backend/server/services/__init__.py` is the central composition point for
long-lived AI services. Routes reuse registered services instead of constructing
parallel pipelines.

## Authentication and RBAC

Authentication uses Flask **server-side** sessions. `backend/server/auth.py`
is the only session owner: it clears/rotates a session after login, stores the
authenticated user as `hau_user`, marks the session permanent, and clears it
on logout. New student sessions require explicit Terms and Conditions
acceptance before `/chat`; the acceptance flag is server-side and the route
rejects missing, false, or expired acceptance. Declining uses logout. Route
guards reuse `require_login`, `require_role`, and `require_any_role`.

| Role | Implemented authority |
| --- | --- |
| Student | Own chatbot activity, appointments, and notifications |
| Guidance staff | Staff appointment, conversation, case-management, settings, analytics, and reports workflows exposed by staff route guards and service checks |
| Administrator | Account management only |

Administrators do not have guidance-record, appointment-state, flagged-case,
counselor-note, referral, intervention, confidentiality, conversation,
escalation, or analytics authority.

## Appointments

Counselors are dynamically selected from a student's current program through
`get_staff_by_program`; appointments do **not** store counselor ownership and
there is no alternate-counselor fallback. The persisted model has a date and a
start time only, so conflict handling is same-date, normalized start-time
equality—not duration or interval-overlap logic.

The service performs early conflict validation for existing error precedence.
The final insert is atomic: the database transaction uses a bounded advisory
lock keyed by the normalized date/time, rechecks blocking appointments, then
inserts or rolls back. Only `pending` and `confirmed` block a slot. The
non-blocking states are `cancelled`, `rejected`, and `completed`. A conflict
returns HTTP `409` and exactly `This schedule is already taken.`

Appointment policy is service-owned:

- consultation schedules are checked only for the dynamically routed counselor;
- Guidance Office availability comes from `appointmentAvailability` settings
  and fails closed when invalid;
- students can cancel or replacement-reschedule only their own pending
  appointments outside the one-hour deadline;
- a replacement is created before its original is cancelled;
- student/replacement appointments start `pending`; manual appointments start
  `confirmed`; and
- lifecycle is `pending → confirmed/rejected/cancelled`, then
  `confirmed → completed/cancelled`; all other states are terminal. Completing
  a confirmed appointment requires nonblank counselor notes.

## Conversations, cases, and notifications

Raw message history is used for the active interaction and finalization; the
authenticated session retains a bounded recent window of up to 50 exchanges
for continuity, using the same bounded text budget as before. Once a
conversation is flagged, its server-owned transcript is retained for the
authorized Guidance staff case review; routine conversation transcripts remain
temporary and are cleared on finalization, logout, expiry, or student device
replacement. Finalization persists the existing
counselor-oriented summary and approved metadata, and may create one
summary-linked escalation. Staff-only case workflows build on flagged
summaries: dedicated counselor notes, internal referrals and append-only
history, interventions and append-only history, and current confidentiality
state with append-only history. Case statuses are visible only to authorized
Guidance staff.

The staff dashboard uses privacy-safe summaries for ordinary Inbox items and
provides the retained raw transcript only inside the authorized detail view of
a flagged case. Inbox presents one current summary item per student/case priority. Flagged
Cases presents authorized pending and reviewed flagged cases, with pending
review clearly distinguished from reviewed status; relevant reviewed history
also remains available in authorized case details. Case Details presents Detected Emotion and Safety
Risk as distinct fields. Crisis or sensitive cases remain pending until review;
routine follow-up must not erase an unresolved flagged case.

Notifications are persistent, recipient-scoped, in-app records. A recipient
marks a notification read explicitly. Notification writes are best-effort and
never roll back an authoritative appointment action.

## AI and chatbot pipeline

```text
Language Detection
→ SafetyService pre-generation checks
→ Conversation Intelligence (intent, emotion, topic, metadata)
→ RAG
→ PromptBuilder
→ LLM generation
→ ResponseSafetyService
→ response/finalization/escalation handling
```

Language support is English, Filipino, and Taglish. Shared lexicon terms are
neutral evidence; Taglish requires exclusive evidence from both languages.
The released emotion model is English-focused; Filipino/Tagalog and Taglish
emotion classification remains a limitation rather than a claim of equivalent
model validation.
SafetyService is authoritative for pre-generation safety and diagnosis-boundary
handling. Explicit immediate danger follows the crisis path. Counselor-approved
warning signs and self-diagnosis requests create a pending Guidance Office
review while retaining a non-emergency supportive response; a review-only case
does not send a high-risk alert. ResponseSafetyService validates generated
output and replaces an unsafe reply as a whole; it does not change escalation
policy. Conversation Intelligence outputs are internal unless an existing API
exposes a current field. The chatbot is not a diagnostic, treatment, or
emergency service. Before chat use, students acknowledge the Guidance Office of
the School of Computing at Holy Angel University scope, message
recording/summarization for guidance support, confidentiality limits for
safety/legal concerns, and immediate-danger directions to local emergency
services or trusted school personnel.

## Analytics and reports

Analytics are read-only and aggregate-only. Appointment and counselor workload
analytics use the authenticated staff member's authorized appointment/program
scope. Referrals and interventions use persisted staff ownership. Chatbot and
flagged-case analytics retain their existing staff-wide aggregate scopes. The
Reports view reuses the four analytics APIs with one shared optional date
range and produces client-side CSV from already-authorized aggregate data.

For endpoint detail, see the [API Reference](api_reference.md). For deployment,
see the [Deployment Guide](../deployment/deployment_guide.md).
