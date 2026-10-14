# CTRL4 Chatbot MK III

> **Development of an AI-Powered Guidance Chatbot for Inquiry Management Using
> NLP-Based Negative Emotion Detection**

[![Release](https://img.shields.io/badge/release-v1.0.7-2f6feb)](https://github.com/jabezapilado/CTRL4_Chatbot_MKIII/releases/tag/v1.0.7)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![Database](https://img.shields.io/badge/database-MySQL%20%7C%20MariaDB-4479A1)
![License](https://img.shields.io/badge/license-Academic%20Use-6f42c1)

## Overview

CTRL4 Chatbot MK III is an undergraduate-thesis Guidance Office support system
for Holy Angel University. It combines authenticated chatbot support,
appointment management, staff case-management workflows, and
privacy-preserving aggregate analytics.

The application uses a JavaScript frontend, Flask, MySQL/MariaDB, and genuine
server-side CacheLib sessions. Its implementation follows:

```text
Frontend → Route → Service → Database
```

## Project status

**Current stable release:** [v1.0.7](https://github.com/jabezapilado/CTRL4_Chatbot_MKIII/releases/tag/v1.0.7)

MK III is the completed, current implementation. Historical roadmaps and MK II
research records remain available for thesis provenance, but they are not the
current system contract.

## Project team and contribution areas

The following contribution areas document the work performed across the CTRL4
thesis project and its successive prototype iterations:

- **Jabez Timothy Apilado** — primary system development, system integration,
  and the completed CTRL4 Chatbot MK III implementation.
- **Teyshaun Zell R. Wylengco** — user-interface and user-experience (UI/UX)
  design.
- **Grant Mihkael Quilantang** — frontend development for CTRL4 Chatbot MK I
  and MK II.
- **Lanix T. Iligan** — public emotion-dataset sourcing and legacy AI-engine
  development.

These descriptions recognize contribution areas; they do not change the
project's existing author notices, license, approval workflow, or maintenance
and security responsibilities.

## Production deployment

Production is deployed on a single persistent VPS with Nginx, Gunicorn, MySQL,
and GitHub Actions deployment from `main`. This preserves server-side sessions,
the provisioned English emotion-model artifact, generated RAG data, and the
production database. Follow the [Deployment Guide](docs/deployment/deployment_guide.md)
for the supported setup and operational checks.

### Docker image and Docker Hub

CTRL4 can also be built as a source-only Docker image and published to Docker
Hub as `jabezapilado/ctrl4-chatbot-mkiii`. The image contains the Flask/Gunicorn
application and its dependencies—not secrets, database data, the controlled
model weight, the generated RAG index, sessions, or logs. Those remain mounted
or configured external runtime assets. Use the Docker section of the
[Deployment Guide](docs/deployment/deployment_guide.md#docker-and-docker-hub)
for the supported build, local run, and VPS migration procedure.

### Self-contained Docker demonstration

The repository also provides a **presentation-only** Docker Compose package
for a local, Gemini-enabled demonstration. It starts an isolated MySQL
container, uses fictitious accounts, and packages the approved model weight
and RAG index into a separately tagged demo image. It never uses the
production database or real user records.

The Gemini API key is supplied only when the container starts. It is never
placed in Git, Docker Hub, the image, or a database volume. The demo profile
does not use XAMPP, a local source checkout, the local model directory, or a
local RAG directory at presentation time.

Maintainers build the demo image from this repository after staging the
approved assets locally (they are intentionally Git-ignored):

```text
demo_assets/model.safetensors
demo_assets/rag_index/knowledge.faiss
demo_assets/rag_index/metadata.json
demo_assets/rag_index/manifest.json
demo_assets/huggingface/hub/models--intfloat--multilingual-e5-large/
```

To build and test the complete demonstration stack locally:

```bash
export CHATBOT_GEMINI_API_KEY='paste-your-key-here'
docker compose -f compose.demo.yaml build
docker compose -f compose.demo.yaml up -d
curl --fail --silent --show-error http://127.0.0.1:5001/health
```

Alternatively, copy `demo.env.example` to a local `demo.env`, enter the key,
and add `--env-file demo.env` to each Compose command. The local file remains
Git-ignored.

After its first tested build has been published as
`jabezapilado/ctrl4-chatbot-mkiii:demo`, a presentation machine needs only
Docker Desktop, internet access, this small Compose file, and a valid Gemini
API key. Download the Compose file, set the key in that terminal session, and
start the demo:

```bash
curl -fsSLO https://raw.githubusercontent.com/jabezapilado/CTRL4_Chatbot_MKIII/dockerization/compose.demo.yaml
export CHATBOT_GEMINI_API_KEY='paste-your-key-here'
docker compose -f compose.demo.yaml pull
docker compose -f compose.demo.yaml up -d
```

Docker pulls the application image and the required MySQL image; no XAMPP
database, CTRL4 source files, local model directory, or local RAG directory is
used by this demo profile.

The demo creates the following public, fictitious accounts in its isolated
database. These credentials are only for the local presentation stack and must
never be reused in a live system.

| Role | Email | Password |
| --- | --- | --- |
| Student | `demo.student@ctrl4.local` | `DemoStudent2026!` |
| Staff | `demo.staff@ctrl4.local` | `DemoStaff2026!` |
| Administrator | `demo.admin@ctrl4.local` | `DemoAdmin2026!` |

To remove the local demo containers and database after a presentation:

```bash
docker compose -f compose.demo.yaml down -v
```

## Features

### AI and chatbot

- English, Filipino, and Taglish interaction at the response/rule level.
- Language Detection, SafetyService, internal intent/emotion/topic/metadata
  processing, RAG, PromptBuilder, and ResponseSafetyService.
- Gemini and Ollama provider support through the existing provider abstraction.
- Guidance Office knowledge retrieval from approved records.
- An externally provisioned English emotion-model artifact; model weights are
  intentionally not stored in ordinary Git history.

The released emotion model is English-focused. Filipino/Tagalog and Taglish
language detection and response rules are implemented, but their emotion
classification should not be treated as equivalent to a separately validated
Filipino or Taglish emotion model.

### Student workflows

- Authenticated chatbot use after accepting the per-session Terms and
  Conditions acknowledgement.
- Appointment booking, history, cancellation, and replacement rescheduling.
- Recipient-scoped in-app notifications.
- Per-reply feedback for students, without storing chatbot reply text in the
  staff feedback view.
- Turn-based chat controls with a short typing indicator for ordinary replies;
  safety escalations remain immediate.
- Server-owned 20-minute idle-chat finalization so closed or abandoned student
  browser sessions do not remain indefinitely as active conversations.
- Gemini output is checked for provider token-limit and visibly unfinished
  replies, with one concise retry before a partial reply can reach a student.
- Responsive student chat layout for compact Android and iPhone viewports,
  including safe-area handling for supported iPhone displays.

### Guidance-staff workflows

- Dynamically program-routed appointment management and manual appointments.
- Appointment lifecycle, counselor notes, and read-only calendar.
- Flagged-case review, case notes, referrals, interventions, and
  confidentiality handling.
- Summary-based Inbox, priority-sorted active Flagged Cases, staff-only
  retained transcripts for flagged-case review, privacy-safe Case Details
  (including separate Detected Emotion and Safety Risk), and Reviewed Case
  History.
- Immediate Inbox visibility for active conversations, with one record updated
  at finalization; pending and reviewed flagged-case views; and privacy-safe
  chatbot feedback review.
- Read-only appointment, chatbot, counselor-workload, and flagged-case
  analytics, plus aggregate-only CSV reports.

### Administrator workflow

- Account management only. Administrators do not receive Guidance Office
  appointments, conversations, case records, notes, analytics, or reports.

## What’s new in MK III

MK III v1.0.7 extends the earlier modular chatbot baseline with appointment
operations, dynamic counselor routing, persistent notifications, case
management, active-conversation Inbox visibility, staff-only flagged-case
transcripts, per-reply feedback, aggregate analytics, CSV reporting,
server-side sessions, release-readiness testing, and deployment documentation.

## Architecture

The chatbot pipeline preserves the following order:

```text
Language Detection
→ SafetyService
→ Conversation Intelligence
→ RAG
→ PromptBuilder
→ LLM generation
→ ResponseSafetyService
→ response/finalization/escalation handling
```

SafetyService remains authoritative for pre-generation crisis and diagnosis
handling. The chatbot does not diagnose, prescribe treatment, or expose hidden
prompts, internal summaries, or protected case data.

For complete ownership, privacy, session, and API details, use the
[documentation index](docs/README.md).

## Technology stack

- **Backend:** Python, Flask, Flask-Session/CacheLib
- **Database:** MySQL or MariaDB
- **AI and retrieval:** PyTorch, Transformers, Sentence Transformers, FAISS,
  Gemini or Ollama
- **Frontend:** HTML, CSS, and JavaScript

## Requirements

- Python 3.10 or newer
- MySQL 8.x or MariaDB
- Git
- Either a configured Gemini provider or a reachable Ollama provider
- Approved Guidance Office knowledge records and the externally provisioned
  English emotion-model artifact

## Quick installation

Use this concise development path; the linked guides remain authoritative for
database upgrade, backup/restore, model provisioning, and production setup.

```bash
git clone https://github.com/jabezapilado/CTRL4_Chatbot_MKIII.git
cd CTRL4_Chatbot_MKIII

python3 -m venv backend/.venv
./backend/.venv/bin/python -m pip install --upgrade pip
./backend/.venv/bin/python -m pip install -r requirements.txt

cp backend/.env.example backend/.env
# Configure backend/.env without committing it.
```

Then prepare a fresh database or follow the backup-first upgrade procedure,
provision the runtime model artifact, build the approved RAG index, and start
the application:

```bash
./backend/.venv/bin/python backend/scripts/verify_emotion_model.py
cd backend
../.venv/bin/python scripts/ingest_guidance_docs.py
../.venv/bin/python app.py
```

Only the approved tokenizer/configuration release at
`ai_engine/models/english/latest` is kept with the source. Historical model
releases and training checkpoints are local archives, not Git or deployment
requirements.

By default, the development server listens at
`http://127.0.0.1:5001`. Verify it with:

```bash
curl --fail --silent --show-error http://127.0.0.1:5001/health
```

### Temporary Tailscale demonstration

For a private, temporary demonstration, the application can be made reachable
without changing code or `backend/.env`. The exported `CTRL4_*` values affect
only the shell that starts Flask and are discarded when that shell exits.

On the demo host, with Tailscale connected, prefer binding to that host's
Tailscale IPv4 address:

```bash
cd backend
export CTRL4_HOST="$(tailscale ip -4)"
export CTRL4_PORT=5001
../.venv/bin/python app.py
```

Run `tailscale ip -4` to obtain the address, then a permitted device in the
same tailnet can open `http://TAILSCALE_IP:5001`. If a specific-interface bind
is unavailable for the local-network setup, `export CTRL4_HOST=0.0.0.0` is the
broader temporary alternative; it can also make the service reachable on the
host's LAN interfaces. Do not use Tailscale Funnel or otherwise expose this
student-support system to the public internet. Stop Flask with `Ctrl+C`; use
`unset CTRL4_HOST CTRL4_PORT` before starting it normally again in the same
terminal.

## MK III operational notes

- The validated local XAMPP MariaDB database is `soc_chatbot`. The MK III audit
  found `db.py`, `backend/sql/schema.sql`, and the live schema structurally
  aligned. Demo chat/case test records were cleaned after a verified SQL backup;
  foundation accounts, settings, program catalog, FAQs, appointment
  availability, and staff profiles remain preserved.
- Versioned database migrations and the audit's nine candidate indexes are
  deferred. The saved `mkiii_startup_hardening_unvalidated.patch` is not part
  of the release and must not be applied as a validated feature.
- Generated RAG artifacts require deliberate review and handling; do not treat
  them as ordinary disposable build output.
- This thesis/demo system has meaningful access, privacy, and request controls,
  but it is not represented as fully production-hardened.

## LLM provider configuration

Configure provider values only in `backend/.env`:

- Use the configured Gemini variables when `CHATBOT_LLM_PROVIDER=gemini`.
- `CHATBOT_GEMINI_TEMPERATURE` controls response variation and
  `CHATBOT_GEMINI_MAX_OUTPUT_TOKENS` bounds a generated reply. Neither setting
  increases the amount of prior conversation retained for an active chat. A
  clipped candidate, including one that consumes its entire output budget while
  reporting a normal stop, receives one concise retry. That retry uses a
  response-only 1,536-token ceiling and asks for a complete response of at
  most 160 words; increasing the normal token limit is not a replacement for
  preserving a complete, focused response.
- Use the configured Ollama URL and model values when
  `CHATBOT_LLM_PROVIDER=ollama`.

Do not place API keys, cookies, database credentials, or production endpoints
in source files or documentation. See the
[Installation Guide](docs/deployment/installation_guide.md) and
[Deployment Guide](docs/deployment/deployment_guide.md) for the supported
environment configuration and single-instance deployment topology.

## Project structure

```text
ai_engine/          AI runtime, knowledge records, and training utilities
backend/            Flask application, services, database helpers, and scripts
docs/               Current references, guides, research provenance, and history
frontend/           Templates and safe client-side presentation
tests/              Contract, integration, privacy, and release-readiness tests
```

## Documentation

- [Documentation index](docs/README.md)
- [Installation Guide](docs/deployment/installation_guide.md)
- [Deployment Guide](docs/deployment/deployment_guide.md)
- [Technical Architecture](docs/architecture/architecture.md)
- [Project Architecture](docs/architecture/project_architecture.md)
- [Security Architecture](docs/architecture/security_architecture.md)
- [API Reference](docs/architecture/api_reference.md)
- [Student Guide](docs/guides/student_guide.md)
- [Guidance Staff Guide](docs/guides/guidance_staff_guide.md)
- [Administrator Guide](docs/guides/administrator_guide.md)
- [Project Context](docs/architecture/project_context.md)
- [Changelog](CHANGELOG.md)

## Project policies

- [Contributing](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [Academic Use License](LICENSE)

## Screenshots

No approved, sanitized release screenshots are currently included. Do not add
screenshots containing student identifiers, appointments, conversations, case
records, notes, credentials, or other protected data.

## Version history

- **MK I:** Initial prototype.
- **MK II:** Modular AI redesign and architecture baseline.
- **MK III:** Current completed system with appointments, case management,
  analytics, security/privacy controls, deployment preparation, documentation,
  and release-readiness verification.

For the complete history, see [CHANGELOG.md](CHANGELOG.md).

## Contributors

Project authors and the academic-use terms are recorded in [LICENSE](LICENSE).
Do not remove or alter original authorship notices.

## License

This repository is provided under the [Academic Use License](LICENSE).
See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution expectations and
[SECURITY.md](SECURITY.md) for private vulnerability reporting.
