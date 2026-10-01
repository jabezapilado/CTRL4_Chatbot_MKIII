# CTRL4 Chatbot MK III — Security, Privacy, RBAC, and Sessions

> **Current reference.** This document describes the controls implemented in
> the supported final-release line (`v1.0.6` and later, including current
> `v1.0.7`). Sprint 10 is historical validation context only; future
> recommendations are not current behavior.

## Implemented access boundaries

CTRL4 has exactly three canonical roles: `student`, `staff`, and `admin`.
Routes enforce authentication and role checks server-side; frontend access
checks are presentation only.

### Students

Students may use their own session/profile, chatbot, own appointments,
permitted cancellation/replacement rescheduling, and own notifications. They
must not receive case statuses, counselor notes, case notes, referrals,
interventions, confidentiality records or reasons, escalation reasons,
conversation summaries, staff analytics, or internal identifiers. A student
must explicitly accept the Terms and Conditions in the
current server session before `/chat` is available; missing, false, or expired
acceptance is rejected server-side. This gate does not apply to staff or
administrator dashboards.

### Guidance staff

Guidance staff may use staff appointment, conversation, case-management,
settings, analytics, and reports workflows exposed by current staff route guards
and service authorization. Appointment visibility remains constrained by the
existing authorized-program/dynamic-routing model where that service applies.
Cross-program case access is denied through the same server-side authorization
and privacy-projection boundaries; a staff member is not granted case access by
client-side navigation alone.
Staff-wide flagged-case analytics are aggregate-only and do not imply personal
reviewer ownership.

### Administrators

Administrators manage accounts. They do not access guidance-specific records,
appointments, appointment lifecycle controls, conversations, flagged cases,
counselor notes, referrals, interventions, confidentiality records, or
analytics.

## Server-side session behavior

The application uses Flask-Session with CacheLib filesystem storage. The browser
receives only an opaque `ctrl4_session` identifier and normal cookie metadata;
authenticated-user data and escalation markers remain server-side.

- `HttpOnly` is enabled.
- `SameSite=Lax` is enabled.
- `Secure` is configurable and required in production.
- Permanent sessions expire after eight hours.
- Login clears and rotates/replaces the session identifier to prevent session
  fixation and issues a new CSRF token; logout clears and invalidates the
  session.
- Student login sets Terms acceptance to unaccepted. The student-only
  `/auth/terms/accept` mutation records explicit acceptance in the server
  session; declining uses the existing logout behavior.
- A student account has one active-device lease. A second-device sign-in first
  receives a confirmation response; an approved replacement finalizes the
  prior browser's server-owned chat through the established summary, safety,
  escalation, and staff-Inbox workflow before the new lease is issued. The
  prior browser is cleared and follows the normal login redirect on its next
  request. The lease stores only session/finalization metadata, never a raw
  transcript. Staff and administrator sessions remain multi-device.
- The currently supported deployment is one application instance. Horizontal
  scaling requires an approved shared server-side session backend first.

## CSRF and cross-origin request protection

Rendered pages receive an opaque CSRF token bound to their server-side session.
The shared browser fetch interceptor sends it only as the `X-CSRF-Token` header
for same-origin `POST`, `PUT`, `PATCH`, and `DELETE` requests. The server
validates the token with constant-time comparison before authenticated
mutations; login validates its pre-authentication page token, and logout is
covered like every other authenticated mutation. `GET`, `HEAD`, and `OPTIONS`
remain read-only and do not require a token. Expired sessions continue to use
the established route-guard response rather than receiving a CSRF error.

The supported thesis deployment is same-origin. Global Flask-CORS middleware is
not enabled, so authenticated endpoints do not send wildcard or credentialed
CORS headers. A cross-origin browser cannot supply the required non-simple
CSRF header without an explicit CORS policy, and therefore cannot perform an
authenticated mutation.

## Data and conversation privacy

Services own privacy projection. Raw chat transcript/history is temporary for
routine conversations; flagged-case transcripts are stored separately in
`flagged_conversation_transcripts` for authorized, program-scoped Guidance
staff review. `conversation_summaries.transcript_json` is not a current
persisted field. Finalized counselor summaries, approved metadata, and
case-management records, including case statuses, are protected staff data.

Protected chat content—including raw messages, generated replies, prompts,
history, summaries, case data, and escalation reasons—is not logged. Raw
messages and generated replies are retained only for flagged cases and only
made available to authorized staff in the existing program-scoped case review.
The browser does not persist raw chat or escalation content in `localStorage` or
`sessionStorage`; obsolete protected keys are cleared when the chatbot starts.

Chatbot feedback is a separate, CSRF-protected student mutation. The browser
receives only an opaque, short-lived response token tied to its server-side
session. Persisted feedback contains the selected category, an optional
500-character note, a one-time token hash, and a server-derived broad reply
context (for example, appointments or academics); it does not contain raw
student messages or generated reply text. Staff retrieval is program-scoped.

The student Terms describe the Guidance Office of the School of Computing at
Holy Angel University scope, message recording and summarization for guidance
support, and confidentiality limits for safety or legal concerns. They do not
represent the chatbot as an emergency service; students in immediate danger are
directed to local emergency services or trusted school personnel.

## Browser safety and API behavior

Persisted and user-controlled dashboard values are rendered with DOM APIs and
`textContent`, not untrusted HTML interpolation. Endpoint-controlled JSON
responses use the established envelopes below. The pre-existing global 404/500
fallback remains a separate implementation detail with its current `error`
payload.

```json
{"success": true, "message": "...", "data": {}}
```

```json
{"success": false, "message": "...", "errors": null}
```

Services own business validation and privacy decisions; database helpers use
parameterized SQL and retain integrity protections such as constraints, enums,
transactions, and the atomic appointment conflict operation.

## AI safety

SafetyService handles pre-generation safety safeguards in the detected language
and remains authoritative for escalation. Explicit immediate danger receives the
crisis response and urgent escalation. Counselor-approved warning signs (for
example hopelessness, worthlessness, social withdrawal, giving away important
belongings, abuse disclosures, and self-diagnosis requests) create a pending
program-scoped Guidance Office review without being mislabeled as an immediate
crisis or sending a high-risk notification. ResponseSafetyService performs
deterministic post-generation checking and replaces an unsafe result without
logging blocked content. The chatbot does not provide medical or psychological
diagnosis, treatment, or prescription authority.

## Deferred security improvements

The following are documented future work, not implemented controls: a shared
session store for multi-instance deployment, versioned database migrations,
deferred database indexes, and environment-specific production hardening.
