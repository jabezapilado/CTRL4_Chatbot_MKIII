# CTRL4 Chatbot MK III — Administrator Guide

> Administrators have account-management authority only. This guide does not
> describe Guidance Office workflows because those records are not available to
> administrator accounts.

Administrators are not guidance-case handlers and do not have chatbot takeover
authority.

## Account management

Use the account-management operations documented in
[API Reference](../architecture/api_reference.md#accounts) to list accounts, apply
the existing role/status filters, and use the approved identifier search. The
`/admin` landing page provides a responsive account-management portal; it is
not a Guidance Office dashboard. Its displayed-account summary always reflects
the accounts returned by the current filters.

Account and program tables show 8 records per page when their current result
set exceeds that number. Use **Previous** and **Next** to navigate the current
filtered or sorted records. Pagination is a display control only and does not
change account-management authority or the underlying records.

The portal supports the approved existing operations:

- create a student, Guidance-staff, or administrator account using the fields
  accepted for the selected role;
- download the student-account CSV template and import up to 500 student
  records at a time;
- update approved role-specific profile fields; and
- deactivate active accounts using the existing role-specific deactivation
  operation.

For CSV onboarding, use the exact UTF-8 columns and order
`full_name,email,gender,program`. The import can create **students only**; it
does not accept roles, account numbers, or passwords. Each row must use an
active program and a unique email address. CTRL4 validates the whole file
before it starts creating accounts, assigns student numbers server-side, and
downloads the generated one-time credentials CSV after a successful import.
Save that download only in the Guidance Office's approved secure location and
provide the temporary credentials privately, because the temporary passwords
are not displayed again.

Unsupported role-specific fields are rejected rather than ignored. Account
roles are selected when creating an account and are not changed by the current
account-update contract. The current API supports deactivation, not
reactivation or destructive deletion. Password hashes are never shown. For an
active student who has forgotten a password, administrators can use the
dedicated **Reset password** action to set and privately provide a new
temporary password. Administrators cannot view an existing password or reset
staff or administrator passwords.

You can update and deactivate student, staff, and administrator accounts using
their dedicated account operations. Administrator accounts cannot retain
student, staff, counselor-profile metadata, or account numbers. You cannot
deactivate your own administrator account. Guidance staff and administrators
remain responsible for their own password updates.

## Access boundary

Administrator accounts cannot access appointments, appointment lifecycle
controls, counselor notes, case notes, conversations, summaries, escalations,
flagged cases, referrals, interventions, confidentiality records, staff
settings, staff analytics, reports, or CSV exports. Use only the account
management functions assigned to the administrator role.

## Session safety

Sign out after account-management work, especially on shared devices. Login and
logout use the application's server-side session; do not share credentials or
browser cookies.
