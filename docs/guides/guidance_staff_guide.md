# CTRL4 Chatbot MK III — Guidance-Staff User Guide

> This guide describes existing staff workflows. It does not grant access beyond
> current staff route guards and service authorization.

## Dashboard and appointments

After sign-in, use the staff dashboard for authorized appointments and
Guidance Office operations. Appointment records visible to you follow the
existing authorized-program/dynamic-routing model; a current program route is
not historical counselor ownership.

The student Terms and Conditions acknowledgement applies only before student
chat access. It does not block or alter staff dashboard workflows.

Staff may create manual appointments for a student using the approved source
and appointment fields. Manual appointments begin **confirmed**. Student
requests begin **pending**. The only appointment lifecycle is:

```text
pending → confirmed | rejected | cancelled
confirmed → completed | cancelled
cancelled, rejected, completed → terminal
```

Only the assigned staff workflow may make a lifecycle transition. A nonblank
counselor note is required before completing a confirmed appointment. Do not
treat start times as duration slots: the current conflict rule is same-date,
normalized start-time equality only.

The month calendar is read-only. It reuses the authorized appointment dataset;
it does not book, move, resize, or link replacement appointments.

## Conversation and case management

The dashboard Inbox shows one current privacy-safe summary item per student.
Flagged Cases shows active pending flagged cases, and
Reviewed Case History retains authorized reviewed records. Staff views do not
expose raw chat transcripts for routine conversations. In a flagged case's
Case Details, the **Conversation Transcript** panel contains the server-captured
student and CTRL4 messages so you can verify the escalation context. This panel
is limited to your authorized programs and must be used only for the Guidance
Office review. Read Detected Emotion and Safety Risk as separate fields.

The staff-only **Priority** indicator is derived from existing case state and
cannot be changed by students: **Critical** is an immediate safety escalation,
**High** is a flagged wellbeing warning-sign review, **Medium** is an active
unflagged conversation, and **Low** is a routine summary. Inbox and Flagged
Cases default-sort by priority and offer priority filters. Critical alerts in
Notifications are visibly marked and state that immediate Guidance Office
review is required.

Case Details uses **Overview** and **Conversation** tabs.
Counselor Notes and Staff Actions remain visible at the top-right. Conversation
is available only for an authorized flagged case.

Staff Actions is independent. Within the right-side Case Records controls, use
**Privacy**, **Referrals**, and **Interventions** to open one management form
at a time instead of scrolling through every form.

The Inbox and Flagged Cases tables show 7 records per page because their
summary rows can be longer. Chatbot Feedback, analytics, and report tables
show 10 records per page. Use **Previous** and **Next** to move through the
current authorized results. Searching, filtering, sorting, or applying a new
analytics date range returns the affected table to its first page; pagination
does not widen program-scoped access or alter records.

Staff can review authorized inquiries, summaries, escalations, and flagged
conversations. Use a flagged case's existing panels to:

- mark a flagged conversation reviewed;
- maintain confidential counselor notes;
- create and update internal referrals and their notes/status history;
- create interventions and record progress or outcomes; and
- view or update the current confidentiality state.

Use **Chatbot Feedback** to review student ratings and optional notes from your
authorized programs. It is a quality-review queue, not an emergency channel,
and intentionally excludes raw chat transcripts and AI reply text. Treat a
repeated category and reply-context signal as evidence to review approved
Guidance Office content, prompts, safety rules, or synthetic regression tests;
do not make the chatbot learn directly from individual student records. The
reply context is a broad server-generated tag, not chat content.

These records are sensitive Guidance Office data. Do not copy them into
unapproved channels. Do not infer a personal reviewer or counselor ownership
where the current record does not persist one.

Crisis or otherwise sensitive cases remain pending until reviewed. A routine
follow-up does not clear an unresolved flagged case. Staff access is
program-scoped; do not attempt to access a student outside your authorized
program scope.

## Settings and notifications

Staff settings include operational configuration. Consultation rooms/schedules
are profile metadata and are validated for appointment routing; they are not a
room-booking system. Guidance Office availability uses the structured
appointment-availability setting. Invalid operational availability data fails
closed for booking.

The notification view is recipient-scoped. Notifications remain until the
recipient explicitly marks them read.

## Analytics, reports, and CSV

The dashboard provides read-only appointment, chatbot, counselor workload, and
flagged-case analytics. Scope differs by module:

- appointment and workload metrics use your authorized appointment/program
  scope; referrals/interventions use persisted staff ownership;
- chatbot and flagged-case analytics are staff-wide aggregates; and
- flagged-case analytics do not establish reviewer ownership.

Reports forward one shared optional date range to the four existing analytics
APIs and export only already-authorized aggregate values as CSV. There are no
raw-data exports or PDF exports.

## Privacy

Student-facing views must never receive staff notes or protected case details.
Use the dashboard only from a protected device and sign out when finished.
