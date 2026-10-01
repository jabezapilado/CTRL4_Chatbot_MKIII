# CTRL4 Chatbot MK III Documentation

This index separates the current CTRL4 Chatbot MK III v1.0.7 implementation
references from research provenance and historical planning material. For
development constraints, follow the repository documentation and current test contracts.

## MK III validated state

The local/demo baseline can use the XAMPP MariaDB database `soc_chatbot`.
Its live schema, `backend/server/db.py`, and `backend/sql/schema.sql` were
structurally aligned in the MK III audit. Production instead uses a separately
provisioned MySQL database on the Contabo VPS with VPS-only credentials; local
demonstration data is never production data. The demo database was cleaned of
operational chat/case test records after a verified SQL backup while foundation
data was retained. Versioned migrations, nine candidate indexes, and the
saved-but-unvalidated startup hardening patch remain deferred work.

Generated RAG indexes and the provisioned production emotion-model artifact
are operational assets. They must be provisioned and verified separately and
are not ordinary source, documentation, or cleanup work.

## Current and authoritative references

### Architecture

- [Technical Architecture](architecture/architecture.md) — comprehensive
  system-level view of the CTRL4 components, technical stack, AI pipeline,
  data/privacy model, and production deployment topology.
- [Project Architecture](architecture/project_architecture.md) — domain
  boundaries, Route → Service → Database ownership, appointments, cases, AI,
  analytics, and reports.
- [Security Architecture](architecture/security_architecture.md) — RBAC,
  CacheLib server-side sessions, privacy projections, browser safety, and
  deferred security work.
- [API Reference](architecture/api_reference.md) — route-derived public page
  and JSON endpoint contracts, authorization, and privacy restrictions.
- [Project Context](architecture/project_context.md) — frozen decisions and
  completed Sprint 1–10 outcomes for contributors.

### Installation and deployment

- [Installation Guide](deployment/installation_guide.md) — concise local setup,
  external model-artifact provisioning, RAG preparation, and development start.
- [Deployment Guide](deployment/deployment_guide.md) — authoritative production
  topology, environment configuration, database preparation, backup/restore,
  logging, Gunicorn procedure, GitHub Actions deployment to the persistent VPS,
  and the private no-code Tailscale demonstration procedure using temporary
  `CTRL4_HOST`/`CTRL4_PORT` exports.

### User guides

- [Student Guide](guides/student_guide.md) — per-session Terms acknowledgement,
  student-only one-device sign-in handling,
  turn-based chat controls, compact mobile layout behavior, appointments,
  notifications, and student privacy boundaries.
- [Guidance Staff Guide](guides/guidance_staff_guide.md) — authorized
  appointment, case-management, settings, analytics, reports, and CSV workflows.
- [Administrator Guide](guides/administrator_guide.md) — account-management-only
  authority and its explicit boundaries.

### Professional review templates

- [Guidance Office response-playbook review](guides/guidance_office_response_playbook_review_template.md)
  — approved student-facing support wording and urgent-contact confirmation.
- [AI professional evaluation](guides/ai_professional_evaluation_template.md)
  — safety routing, response quality, retrieval, model limits, and AI
  evaluation review.
- [Web professional evaluation](guides/web_professional_evaluation_template.md)
  — student/staff UX, responsive design, accessibility, frontend security, and
  role-boundary review.

## Research and provenance references

- [Emotion Label Lineage Report](research/emotion_label_lineage_report.md) —
  source-to-label transformation and runtime label mapping.
- [Model and evaluation provenance](models/README.md) — historical
  English/Filipino model documentation, tracked evaluation artifacts, and the
  verified current-runtime v10 model card, integrity record, and held-out
  evaluation record. This code-adjacent path is retained because the training
  publication workflow owns it; its contents are research records, not
  deployment instructions or model binaries.

## Roadmaps and historical material

- [MK III roadmap](roadmap/mkiii_roadmap.md) — historical planning for the MK III
  program; frozen implementation takes precedence.
- [Historical MK II roadmaps](roadmap/README.md) — preserved planning artifacts.
- [Historical archive](archive/README.md) — superseded dataset, design, ethics,
  API, and Sprint 3 records retained for thesis provenance.

## Release information

- [Root README](../README.md) — project overview and quick start.
- [Changelog](../CHANGELOG.md) — concise release history.
- [v1.0.7 release tag](https://github.com/jabezapilado/CTRL4_Chatbot_MKIII/releases/tag/v1.0.7)
  — current stable release.

Historical documents intentionally retain their original terminology, including
MK II references. They do not define current roles, APIs, data retention,
analytics, deployment behavior, or permissions.
