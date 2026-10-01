# CTRL4 Chatbot MK III — Current API Reference

> **Current reference, derived from route decorators.** All examples are
> synthetic. Do not send credentials, session identifiers, or protected case
> data in URLs. Unless noted, successful responses use
> `{"success": true, "message": "...", "data": ...}`; failures retain the
> established `errors: null` envelope (appointment required-field failures may
> include their existing field map).

Endpoint-controlled errors use the established envelope. The current Flask
global 404/500 fallback handlers retain their pre-existing `{"error": "..."}`
payload; they are not a documented alternative endpoint contract and were not
redesigned by this documentation issue.

All `POST`, `PUT`, `PATCH`, and `DELETE` requests made from a browser session,
including login, must send the page bootstrap `X-CSRF-Token` header. The shared
browser fetch layer supplies it for same-origin requests. Token failures return
the standard JSON envelope with HTTP 403.

## Rendered frontend routes

These are page routes, not JSON APIs. Their server-side route guard redirects
unauthenticated users to login and enforces the listed role boundary.

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| GET | `/` | Public | Login page |
| GET | `/login` | Public | Login page |
| GET | `/chatbot` | Student | Student chatbot |
| GET | `/appointment` | Student | Student appointment page |
| GET | `/dashboard` | Guidance staff | Staff dashboard |
| GET | `/admin` | Administrator | Account-management portal only |

## Authentication and health

| Method | Path | Access | Request | Success / important errors |
| --- | --- | --- | --- | --- |
| POST | `/auth/login` | Public | `email`, `password`; optional `replace_existing_session` boolean | 200 authenticated user in `data`; 400 validation, 401 invalid credentials, 403 blocked account; 409 active student session requires confirmation; 503 prior conversation could not be safely finalized |
| POST | `/auth/terms/accept` | Student | None | 200 marks the current server session as accepted; 401 no session, 403 non-student |
| POST | `/auth/logout` | Authenticated | None | 200; 401 if no session |
| GET | `/health` | Public | None | 200 service status; 500 only on health failure |

Login establishes the server-side session. The returned account data supports
the existing frontend redirect; the browser cookie is opaque and must not be
treated as an API credential to inspect. Students must explicitly accept the
Terms and Conditions in each new server session before chatbot access; declining
uses the existing logout flow.

For a student-only active-device conflict, a login without
`replace_existing_session: true` returns the normal error envelope with `409`.
After explicit confirmation, CTRL4 finalizes the prior browser's active
conversation with the same server-owned workflow used for normal finalization,
then creates the new student's session. Staff and administrator logins do not
use this confirmation flow.

## Accounts

Administrators manage accounts only; account-management APIs do not grant
guidance-record access. All endpoints in the following table require `admin`.

| Method | Path | Request / query | Success | Important errors |
| --- | --- | --- | --- | --- |
| GET | `/api/accounts` | Optional `role`, `status`, `q` | 200 `data.items` | 400 invalid filters |
| POST | `/api/accounts` | See role-specific creation fields below | 201 id/status and generated number when applicable | 400 validation/unsupported fields; 409 duplicate email |
| POST | `/api/accounts/import/students` | Multipart `file`: UTF-8 CSV with exact headers `full_name,email,gender,program` | 201 imported `data.items` with one-time temporary credentials | 400 missing/invalid file, malformed rows, inactive program, or duplicate rows; 409 duplicate email |
| PATCH | `/api/accounts/<account_id>` | Student fields: `full_name`, `email`, `gender`, `program` | 200 updated account | 400, 404, 409 |
| DELETE | `/api/accounts/<account_id>` | None | 200 disabled status | 400, 404 |
| PATCH | `/api/accounts/staff/<account_id>` | Approved staff profile fields | 200 updated account | 400, 404, 409 |
| DELETE | `/api/accounts/staff/<account_id>` | None | 200 disabled status | 400, 404 |
| PATCH | `/api/accounts/admin/<account_id>` | Approved administrator profile fields | 200 updated account | 400, 404, 409 |
| DELETE | `/api/accounts/admin/<account_id>` | None | 200 disabled status | 400, 404; self-deactivation is rejected |

Every creation payload has `full_name`, `email`, `password`, and `role` (the
role defaults to `student` only when omitted). A student may provide `gender`
and `program`. A staff account may provide `gender`, `assigned_programs`,
`office`, `support_statement`, `consultation_rooms`, and
`consultation_schedules`. An administrator may provide `gender` only; student,
staff, counselor-profile, and account-number fields are rejected. The listing
search composes with role/status and searches only approved identifier fields.

The student CSV import is limited to 500 nonblank rows and 1 MB. It creates
only student accounts, assigns account numbers server-side, and deliberately
does not accept a role, student number, or password column. Its successful
response contains the temporary passwords exactly once so the administrator
portal can immediately create a credentials download; neither password hashes
nor those temporary passwords are exposed by subsequent account APIs.

### Manual-booking student search — staff only

| Method | Path | Request / query | Success / privacy |
| --- | --- | --- | --- |
| GET | `/api/accounts/search` | Optional `q` | 200 matching student `data.items`; omitted/blank query returns an empty list |

This search supports the existing staff manual-appointment workflow. It is not
an administrator account listing and does not change staff guidance-record
authority.

## Appointments

| Method | Path | Access | Request | Success / important errors |
| --- | --- | --- | --- | --- |
| GET | `/api/appointments` | Staff | None | 200 authorized `data.items` |
| POST | `/api/appointments` | Authenticated student booking flow | `contact_number`, `appointment_category`, `appointment_mode`, `preferred_date`, `preferred_time_slot`, `reason` | 201; 400 validation, 404 missing student, 409 exact slot conflict |
| GET | `/api/appointments/my` | Student | None | 200 own `data.items`; counselor notes are redacted |
| PATCH | `/api/appointments/my/<appointment_id>/cancel` | Student owner | None | 200; 403 ownership, 404 missing, 400 lifecycle/deadline rule |
| POST | `/api/appointments/my/<appointment_id>/reschedule` | Student owner | `preferred_date`, `preferred_time_slot` | 201 replacement id; 403/404/400 or 409 conflict |
| POST | `/api/appointments/manual` | Staff | `account_id`, `appointment_category`, `appointment_mode`, `preferred_date`, `preferred_time_slot`, `reason`, `appointment_source` | 201; 400/404/409 |
| PATCH | `/api/appointments/<appointment_id>` | Assigned staff | `status` | 200; 400 invalid transition, 404 missing |
| GET | `/api/appointments/<appointment_id>` | Staff | None | 200 authorized details; 404 missing |
| PATCH | `/api/appointments/<appointment_id>/notes` | Assigned staff | `counselor_notes` | 200; 400/404 |

The only appointment statuses are `pending`, `confirmed`, `cancelled`,
`rejected`, and `completed`. Normalized same-date start-time conflicts block
only `pending` and `confirmed` and return HTTP 409 with
`This schedule is already taken.` There is no duration/end-time API.

## Chatbot and conversation finalization

| Method | Path | Access | Request | Success / important errors |
| --- | --- | --- | --- | --- |
| POST | `/chat` | Student with accepted Terms | `message`; optional in-memory `conversation` | 200 response data; 400 missing message; 401 no session; 403 Terms not accepted |
| POST | `/chat/feedback` | Student with accepted Terms | session-issued `response_token`, feedback `category`, optional ≤500-character `comment` | 201; 400 expired token/invalid input; 401 no session; 403 role/Terms/CSRF failure |
| POST | `/chat/finalize` | Authenticated | non-empty `conversation`; optional `topic`, `language`, `emotion` | 200 finalization data; 400 missing conversation; 401 no session |

The public chat contract exposes only its existing response fields. Internal
intent, normalized topic, normalized emotion, metadata, prompts, and retrieval
details are not API inputs or historical analytics fields.

The feedback token is opaque, short-lived, and session-owned. Feedback stores a
category, optional note, and server-derived broad reply context only; it does
not persist raw student messages or AI reply text. It is not an emergency
reporting channel.

The student Terms and Conditions describe the Guidance Office of the School of
Computing at Holy Angel University scope. They state that messages may be
recorded and summarized for guidance support, that a flagged conversation may
be retained for authorized counselor review, confidentiality has safety/legal
limits, and immediate danger requires local emergency services or trusted
school personnel. The acknowledgement does not apply to staff or administrator
dashboards.

## Notifications and settings

| Method | Path | Access | Request | Success / important errors |
| --- | --- | --- | --- | --- |
| GET | `/api/notifications` | Student or staff | None | 200 recipient-scoped `data.items` |
| PATCH | `/api/notifications/<notification_id>/read` | Student or staff recipient | None | 200; 404 for inaccessible/missing item |
| GET | `/api/settings` | Staff | None | 200 current settings |
| POST | `/api/settings` | Staff | settings payload | 200 saved status |
| GET | `/api/settings/faqs` | Staff | None | 200 `data.items` persisted FAQ entries |
| POST | `/api/settings/faqs` | Staff | title, question, answer; optional active/order | 201 created FAQ; 400 validation |
| PATCH | `/api/settings/faqs/<faq_id>` | Staff | title, question, answer, active, or order | 200 updated FAQ; 400 validation; 404 |
| DELETE | `/api/settings/faqs/<faq_id>` | Staff | None | 200 removed status; 404 |

Settings include staff-maintained operational configuration. The descriptive
`officeHours` value is informational; booking availability uses the validated
`appointmentAvailability` configuration in the appointment service. Active FAQ
entries are persisted Guidance Office knowledge and are evaluated after live
operational settings but before RAG or provider output.

## Account and program management

| Method | Path | Access | Request | Success / important errors |
| --- | --- | --- | --- | --- |
| GET | `/api/accounts/programs` | Admin | None | 200 active and inactive program catalog |
| GET | `/api/accounts/programs/active` | Admin or staff | None | 200 active program catalog |
| POST | `/api/accounts/programs` | Admin | code, display_name; optional active/order | 201; 400 validation |
| PATCH | `/api/accounts/programs/<program_code>` | Admin | display_name, active, or order | 200; 400 validation; 404 |
| GET | `/api/accounts/staff/profile` | Staff | None | 200 authenticated staff operational profile only |
| PATCH | `/api/accounts/staff/profile` | Staff | office, support statement, rooms, schedules | 200; 400 validation |

Administrators manage account identity, role, account authorization, and active
program assignments. Guidance operational profiles are self-service staff data;
administrator account routes reject office, support-statement, consultation-room,
and consultation-schedule writes.

## Conversation, escalation, and case management — staff only

Every endpoint in this section requires `staff`. Returned data is staff
privacy-projected; student APIs do not receive these records.

| Method | Path | Request | Success / important errors |
| --- | --- | --- | --- |
| GET | `/api/staff/inbox` | None | 200 current authorized student summary items, one latest item per student |
| GET | `/api/staff/inbox/<summary_id>` | None | 200 privacy-projected summary detail; 404 outside staff program scope or missing |
| GET | `/api/staff/inbox/<summary_id>/history` | None | 200 reviewed flagged-case history for the same authorized student; 404 outside staff program scope or missing |
| GET | `/api/flagged-conversations/<summary_id>/transcript` | None | 200 server-owned raw transcript for the flagged case; 404 outside staff program scope, non-flagged, or missing; never available to students or administrators |
| GET | `/api/staff/chatbot-feedback` | None | 200 ratings, optional notes, broad reply contexts, and scoped aggregate quality signals; no raw chat/AI reply text |
| GET | `/api/inquiries` | None | 200 `data.items` |
| GET | `/api/conversation-summaries` | None | 200 `data.items` |
| GET | `/api/escalations` | None | 200 `data.items` |
| GET | `/api/flagged-conversations` | None | 200 `data.items` |
| GET | `/api/flagged-conversations/<summary_id>` | None | 200 case projection; 404 |
| PATCH | `/api/flagged-conversations/<summary_id>/review` | None | 200; 404; 409 when already reviewed |
| GET | `/api/flagged-conversations/<summary_id>/confidentiality` | None | 200; 404 |
| PATCH | `/api/flagged-conversations/<summary_id>/confidentiality` | `confidentiality_status`, optional `confidentiality_reason` | 200; 400/404 |
| GET | `/api/flagged-conversations/<summary_id>/notes` | None | 200 `data.items`; 404 |
| POST | `/api/flagged-conversations/<summary_id>/notes` | `note_text` | 201; 400/404 |
| PATCH | `/api/flagged-conversations/<summary_id>/notes/<note_id>` | `note_text` | 200; 400/404 |
| GET | `/api/flagged-conversations/<summary_id>/referrals` | None | 200 `data.items`; 404 |
| POST | `/api/flagged-conversations/<summary_id>/referrals` | `destination`, `referral_reason`, optional `note_text` | 201; 400/404 |
| PATCH | `/api/flagged-conversations/<summary_id>/referrals/<referral_id>/status` | `status` | 200; 400/404 |
| POST | `/api/flagged-conversations/<summary_id>/referrals/<referral_id>/notes` | `note_text` | 201; 400/404 |
| GET | `/api/flagged-conversations/<summary_id>/interventions` | None | 200 `data.items`; 404 |
| POST | `/api/flagged-conversations/<summary_id>/interventions` | `intervention_type`, `objective` | 201; 400/404 |
| PATCH | `/api/flagged-conversations/<summary_id>/interventions/<intervention_id>/progress` | `progress_status` | 200; 400/404 |
| PATCH | `/api/flagged-conversations/<summary_id>/interventions/<intervention_id>/outcome` | `outcome` | 200; 400/404 |

Inbox and ordinary case endpoints return privacy-projected summaries. The
flagged-case transcript endpoint is the sole staff-only raw-transcript view.
Active Flagged Cases are pending cases; reviewed records are available through
the authorized inbox-history flow. A staff member outside the student's
authorized program scope receives the existing not-found response.

## Dashboard analytics — staff only

All analytics endpoints accept optional inclusive `start_date` and `end_date`
where the service supports filtering. Malformed or reversed ranges return 400.
They return aggregate-only data; no endpoint exposes raw case or conversation
records for analytics.

| Method | Path | Scope / data |
| --- | --- | --- |
| GET | `/api/dashboard/appointments/analytics` | Staff-authorized appointment dataset; total/status/trends/current dynamic-routing counselor and program counts |
| GET | `/api/dashboard/chatbot/analytics` | Existing staff-wide aggregates: total messages, trends, finalization and escalation counts, persisted `emotion_result` distribution, average finalized message count |
| GET | `/api/dashboard/counselor-workload` | Authenticated staff's authorized appointments and persisted staff-owned referrals/interventions |
| GET | `/api/dashboard/flagged-cases/analytics` | Staff-wide aggregate flagged-case counts, escalation trends, persisted status distribution, current confidentiality count |
| GET | `/api/dashboard/stats` | Existing staff dashboard statistics |

The Reports view directly reuses the four analytics endpoints above and creates
CSV only from their already-authorized aggregate values. PDF export is not
implemented.
