# CTRL4 Chatbot MK III — Deployment Guide

This guide is the supported, reproducible deployment procedure for CTRL4
Chatbot MK III. It preserves the implemented Flask, MySQL/MariaDB, RAG, and
server-side session architecture; it does not change application behavior.

## Supported deployment topology

The supported topology is **one application instance on one host**. CTRL4 uses
CacheLib filesystem sessions, so a browser session is valid only for the single
application process that owns the configured session directory. Do not run
multiple Gunicorn workers, multiple containers, or multiple hosts until a
separately approved shared session backend is introduced.

Run TLS at a trusted reverse proxy. In production the application requires
secure cookies and therefore must receive HTTPS requests from that proxy.

## Prerequisites

- Python 3.10 or newer
- MySQL 8.x or MariaDB, including `mysql` and `mysqldump` client commands
- Git
- A Guidance Office knowledge-base directory, a validated RAG index, and the
  protected English emotion-model release artifact
- Either a Gemini API key or a reachable Ollama instance
- For production: a reverse proxy that terminates HTTPS

## Docker and Docker Hub

CTRL4 supports a Docker image for reproducible application packaging. Docker
Hub stores that image; it is not a replacement for the VPS, Nginx, the
provisioned MySQL instance, or the protected AI/runtime assets.

The image installs the official CPU-only PyTorch wheel because CTRL4's current
VPS performs CPU inference. It does not bundle NVIDIA CUDA libraries.

The image deliberately contains only application source and Python runtime
dependencies. Never include or upload the following in an image, Docker Hub
repository, Compose file, or Git commit:

- `backend/.env`, API keys, database passwords, session secrets, or SSH keys;
- MySQL/MariaDB data or SQL backups;
- `model.safetensors` or historical model checkpoints;
- the generated RAG index, operational logs, filesystem sessions, student
  data, staff records, uploads, screenshots, or local research material.

The repository's `.dockerignore` enforces the source-image boundary. The
`compose.yaml` runs a single app container only. It intentionally does not add
a database, Nginx, or public management service, because the supported
production topology retains those existing protected services.

### Build and test locally

Install Docker Desktop and sign in to Docker Hub. The project owner's Docker
Hub namespace is `jabezapilado`; the image repository is
`ctrl4-chatbot-mkiii`.

The container connects to a MySQL instance already running on the host by
default. On Docker Desktop for Mac, `host.docker.internal` reaches the host.
On Linux Compose supplies the same name through the `host-gateway` mapping. If
MySQL is on another host, set `CTRL4_DB_HOST` to that private hostname or IP.

Prepare the ordinary VPS/local `backend/.env` first; it remains untracked.
Then build and start one local app container:

```bash
docker compose build
docker compose up -d
docker compose ps
curl --fail --silent --show-error http://127.0.0.1:5001/health
```

The default Compose mounts are local `runtime/sessions`, `runtime/logs`, the
existing `backend/data/rag_index`, and the controlled model weight at
`ai_engine/models/english/latest/model.safetensors`. Override paths without
editing Compose, for example:

```bash
CTRL4_RUNTIME_DIR=/secure/ctrl4-runtime \
CTRL4_RAG_INDEX_DIR=/secure/ctrl4-rag-index \
CTRL4_MODEL_WEIGHTS=/secure/ctrl4-model/model.safetensors \
docker compose up -d
```

If the container cannot connect to MySQL, do not weaken database access or
expose port 3306. Verify the configured `CHATBOT_DB_HOST`, the existing
database user's permitted host, and private network reachability instead.

Stop only the application container with:

```bash
docker compose down
```

That command does not remove the host-mounted database, model, RAG index,
sessions, or logs.

### Publish a tested image to Docker Hub

Use a meaningful immutable tag, preferably the Git commit short SHA or an
approved release tag. Do not rely only on `latest` for a production rollback.

```bash
IMAGE=jabezapilado/ctrl4-chatbot-mkiii
TAG=$(git rev-parse --short HEAD)

docker build --platform linux/amd64 --tag "$IMAGE:$TAG" .
docker push "$IMAGE:$TAG"
docker tag "$IMAGE:$TAG" "$IMAGE:latest"
docker push "$IMAGE:latest"
```

The `linux/amd64` platform matches the current VPS. On Apple Silicon, Docker
Desktop may build this through emulation; expect the first build to take
longer. Confirm the tag appears in Docker Hub before any server change.

### Production migration boundary

Moving the VPS from systemd-managed Gunicorn to Docker Compose is a separate,
reviewed production change. Before switching traffic, back up MySQL and retain
the current systemd unit as a rollback path. Preserve Nginx as the HTTPS
reverse proxy and bind the container only to `127.0.0.1:5001`; do not publish
additional ports. Configure Compose on the VPS to pull a specific image tag,
mount the existing protected model/RAG/session/log locations, and retain the
VPS-only `backend/.env` outside source control.

Update the GitHub Actions deployment workflow only after a verified manual VPS
cutover. It currently deploys the systemd/Gunicorn topology, so it must not be
used to restart a Docker container until that reviewed workflow change is in
place.

## Dependencies

`requirements.txt` at the repository root is the **sole authoritative runtime
dependency manifest**. `backend/requirements.txt` only delegates to it for
legacy commands.

From the repository root:

```bash
python3 -m venv backend/.venv
./backend/.venv/bin/python -m pip install --upgrade pip
./backend/.venv/bin/python -m pip install -r requirements.txt
```

The documented setup command remains valid because it delegates to the same
manifest:

```bash
cd backend
./setup.sh
```

## Environment configuration

Create `backend/.env` by copying `backend/.env.example`. The application loads
this file automatically; do **not** shell-source it because values may contain
spaces or special characters.

```bash
cp backend/.env.example backend/.env
chmod 600 backend/.env
```

Important variables are listed below. `.env.example` contains the complete
reference, including optional seed-account and RAG tuning values.

| Group | Required production values |
| --- | --- |
| Runtime | `CHATBOT_ENV=production`, `CHATBOT_DEBUG=false`, a strong unique `CHATBOT_SECRET_KEY`, and `CHATBOT_PORT` (default `5001`) |
| Database | `CHATBOT_DB_HOST`, `CHATBOT_DB_PORT`, `CHATBOT_DB_USER`, `CHATBOT_DB_PASSWORD`, `CHATBOT_DB_NAME`; optionally `CHATBOT_DB_SSL_CA` and `CHATBOT_DB_SSL_VERIFY_CERT=true` |
| Sessions | `CHATBOT_SESSION_TYPE=cachelib`, an absolute protected `CHATBOT_SESSION_FILE_DIR`, `CHATBOT_SESSION_COOKIE_SECURE=true`, and `CHATBOT_STUDENT_CHAT_IDLE_TIMEOUT_SECONDS=1200` |
| Logging | an absolute protected `CHATBOT_LOG_FILE`, `CHATBOT_LOG_LEVEL`, `CHATBOT_LOG_MAX_BYTES`, and `CHATBOT_LOG_BACKUP_COUNT` |
| Database startup | `CHATBOT_DATABASE_INITIALIZE_ON_START=false`; perform upgrades explicitly after backup |
| AI | `CHATBOT_LLM_PROVIDER`, Gemini values when using Gemini, or Ollama URL/model when using Ollama. `CHATBOT_GEMINI_TEMPERATURE` controls response variation; `CHATBOT_GEMINI_MAX_OUTPUT_TOKENS` limits reply length, not active-chat context. Gemini retries one visibly incomplete or output-budget-exhausted candidate once with a concise-completion requirement and a response-only 1,536-token ceiling. |
| RAG | `CHATBOT_RAG_DOCS_DIR`, `CHATBOT_RAG_INDEX_DIR`; set `CHATBOT_RAG_AUTO_BUILD_ON_START=false` after provisioning the index |

Production startup rejects unsafe combinations: debug mode, the default secret,
non-secure session cookies, a missing session directory, or automatic startup
migrations without `CHATBOT_DATABASE_BACKUP_CONFIRMED=true`.

Development behavior is unchanged: `CHATBOT_ENV` defaults to `development`,
debug defaults to `true`, and database initialization remains enabled by
default.

### Server-owned idle student-chat finalization

Browsers cannot reliably run logout JavaScript after a tab is closed or a
phone sleeps. Production therefore runs a small **VPS-local** timer every
minute. It finalizes a student conversation only after the configured period
without a completed chat exchange (20 minutes by default), preserves the
existing final summary and escalation workflow, clears the active student
lease, and retains a transcript only when the conversation is flagged for
authorized Guidance Office review.

The internal endpoint is bound to Gunicorn's loopback listener and requires a
private header value. Set a dedicated value in the VPS-only `backend/.env`
when possible:

```ini
CHATBOT_STUDENT_CHAT_IDLE_TIMEOUT_SECONDS=1200
CHATBOT_STUDENT_CHAT_IDLE_FINALIZER_KEY=replace-with-a-long-random-secret
```

If the finalizer key is absent, CTRL4 uses the required `CHATBOT_SECRET_KEY`
only for the loopback maintenance call. Never put either value in GitHub,
browser code, or a command copied into a public shell history.

Install the tracked timer units once on the VPS after the application code has
been deployed:

```bash
sudo install -m 644 /srv/ctrl4/app/docs/deployment/systemd/ctrl4-idle-finalizer.service \
  /etc/systemd/system/ctrl4-idle-finalizer.service
sudo install -m 644 /srv/ctrl4/app/docs/deployment/systemd/ctrl4-idle-finalizer.timer \
  /etc/systemd/system/ctrl4-idle-finalizer.timer
sudo systemctl daemon-reload
sudo systemctl enable --now ctrl4-idle-finalizer.timer
systemctl list-timers ctrl4-idle-finalizer.timer
```

Verify a manual safe run without printing its secret:

```bash
sudo systemctl start ctrl4-idle-finalizer.service
sudo journalctl -u ctrl4-idle-finalizer.service -n 20 --no-pager
```

The timer reads the VPS-only environment file and connects only to
`127.0.0.1:5001`. Do not publish this maintenance endpoint through Nginx or
add a public firewall rule for it.

### Temporary survey student registration

Student self-registration is disabled by default. To open it only for an
approved survey window, add these values to the VPS-only `backend/.env` file:

```ini
CHATBOT_STUDENT_SELF_REGISTRATION_ENABLED=true
CHATBOT_STUDENT_SELF_REGISTRATION_CODE=use-a-private-random-survey-code
```

Restart the application after changing the file:

```bash
sudo systemctl restart ctrl4
sudo systemctl status ctrl4 --no-pager
```

The public `/register` page is available only while both values are set. It
creates **student** accounts only, accepts active programs and
`@student.hau.edu.ph` email addresses, generates the student number on the
server, and keeps the regular sign-in and Terms acknowledgement flow. Student
number allocation safely retries a collision when several participants submit
registration at once. Do not commit the registration code, share it outside
the survey participants, or use it as a replacement for account
administration.

Immediately after the survey, close registration and restart the service:

```ini
CHATBOT_STUDENT_SELF_REGISTRATION_ENABLED=false
```

If a survey participant forgets their password, an administrator can select
**Reset password** beside that student in **Account Management**. Enter and
confirm a new temporary password, then provide it privately to that student.
The old password cannot be viewed or recovered, and the normal account-edit
form does not change passwords.

## MySQL client credentials for backup and restore

Do not put database passwords on a command line. Create a restricted client
defaults file outside the repository, for example `/etc/ctrl4/mysql-client.cnf`:

```ini
[client]
host=127.0.0.1
port=3306
user=CTRL4_DATABASE_USER
password=CTRL4_DATABASE_PASSWORD
```

If the database requires TLS, add the supported client TLS options to that
file. Restrict it to its owner:

```bash
chmod 600 /etc/ctrl4/mysql-client.cnf
```

Set `CTRL4_MYSQL_DEFAULTS_FILE` to this file only for the backup or restore
command. It is never written to application configuration or logs.

## Private production database UI access

Do not expose MySQL or phpMyAdmin to the public internet. To use a local
database UI such as VS Code Database Client, DBeaver, or TablePlus, open an SSH
tunnel from the repository root:

```bash
./scripts/open-production-db-tunnel.sh
```

The script forwards only the local endpoint `127.0.0.1:3307` to MySQL's
VPS-local endpoint `127.0.0.1:3306`. It contains no database credentials; the
normal SSH authentication prompt or configured SSH key is still required.
Leave the terminal open while the database UI is in use, then press `Ctrl+C` to
close the tunnel. Its default host is the provisioned VPS address so SSH can
use the operator-verified host key; the website domain is not used for this
SSH connection.

Configure the database UI with:

| Field | Value |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `3307` |
| Database | the production database name, for example `soc_chatbot` |
| Username | the database-scoped application or read-only database user |
| Password | enter in the UI; do not save it in this repository |

If local port `3307` is occupied, choose another local-only port without
changing MySQL or the firewall:

```bash
CTRL4_TUNNEL_PORT=3308 ./scripts/open-production-db-tunnel.sh
```

The host and SSH user may also be overridden for a future approved production
host change with `CTRL4_TUNNEL_HOST` and `CTRL4_TUNNEL_USER`.

### Optional phpMyAdmin through the same private access pattern

phpMyAdmin is optional and must never be served on the public CTRL4 domain.
If a browser database UI is needed, install it on the VPS with PHP-FPM and bind
its Nginx server to `127.0.0.1:8081` only. During the `phpmyadmin` package
installation, select **no web server** and decline `dbconfig-common`; CTRL4's
existing MySQL application account remains the only database credential used
to sign in.

After the server-side setup, open it only through the local helper:

```bash
./scripts/open-production-phpmyadmin.sh
```

Then open `http://127.0.0.1:8080/` in a local browser and sign in with a
database-scoped user such as `ctrl4_app`. Do not use the MySQL `root` account.
The script forwards the browser connection to VPS-local port `8081`; neither
phpMyAdmin nor MySQL receives a public firewall rule or public DNS record.

If the local browser port is occupied:

```bash
CTRL4_PHPMYADMIN_TUNNEL_PORT=8082 ./scripts/open-production-phpmyadmin.sh
```

### Optional Cockpit VPS administration UI

Cockpit provides a browser UI for VPS health, storage, logs, updates, and
service status. Install and enable it on Ubuntu:

```bash
sudo apt install cockpit
sudo systemctl enable --now cockpit.socket
```

Do not add a public firewall rule for Cockpit's port `9090`. Open it through
the local helper instead:

```bash
./scripts/open-production-cockpit.sh
```

Open `https://127.0.0.1:9090/` and sign in with the VPS Linux account, such as
`ctrl4`. Cockpit uses a server-local certificate, so a browser warning is
expected for `127.0.0.1`; confirm that the address is exactly the local URL
shown by the helper before proceeding. Cockpit has system administration
authority, so do not share this tunnel or its VPS credentials.

If the local port is occupied:

```bash
CTRL4_COCKPIT_TUNNEL_PORT=9091 ./scripts/open-production-cockpit.sh
```

## Database initialization

### Fresh database — authoritative schema procedure

Use `backend/sql/schema.sql` only for a fresh, empty database. It contains the
complete current schema and intentionally does not select a hard-coded database
name.

```bash
export CTRL4_MYSQL_DEFAULTS_FILE=/etc/ctrl4/mysql-client.cnf
mysql --defaults-extra-file="$CTRL4_MYSQL_DEFAULTS_FILE" \
  -e 'CREATE DATABASE ctrl4_development CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'
mysql --defaults-extra-file="$CTRL4_MYSQL_DEFAULTS_FILE" ctrl4_development \
  < backend/sql/schema.sql
```

Set `CHATBOT_DB_NAME=ctrl4_development` in `backend/.env`. The application may
then start with initialization disabled in production because the complete
schema already exists.

### Existing database — controlled maintenance only

The MK III audit found the live XAMPP MariaDB `soc_chatbot` schema structurally
aligned with `db.py` and `schema.sql`. Its local demo cleanup removed only
operational chat/case test data after a verified SQL backup and retained
foundation accounts, settings, program catalog, FAQs, appointment availability,
and staff assignments/rooms/schedules.

`initialize_database()` remains legacy compatibility code, not a versioned
migration framework or an approved routine-maintenance command. Migration work
and nine candidate indexes identified by the audit are deferred. Do not run it
against an existing database without an approved maintenance plan and backup.

Before invoking it against an existing database:

1. Stop the application.
2. Create and verify a backup using the procedure below.
3. Set `CHATBOT_DATABASE_BACKUP_CONFIRMED=true` temporarily.
4. Run the initializer explicitly:

   ```bash
   cd backend
   CHATBOT_DATABASE_BACKUP_CONFIRMED=true \
     ../.venv/bin/python scripts/setup_database.py
   ```

5. Verify `/health`, required tables, and the canonical appointment status
   values before restarting normal production traffic.

In production, `setup_database.py` refuses to run unless the backup-confirmation
environment value is set. It does not seed accounts unless `--seed` is supplied
explicitly. In development, its existing seed behavior is retained.

Do not set `CHATBOT_DATABASE_INITIALIZE_ON_START=true` for routine production
starts. If an operator deliberately enables it, the same backup confirmation is
required by configuration validation.

## Backup and restore

### Backup

Backups are logical SQL dumps. The script refuses to overwrite an existing
file, writes through a restricted temporary file, and does not include
credentials in process arguments.

```bash
export CTRL4_MYSQL_DEFAULTS_FILE=/etc/ctrl4/mysql-client.cnf
./backend/scripts/backup_database.sh \
  /secure/ctrl4-backups/ctrl4_$(date +%Y%m%d_%H%M%S).sql
```

Store backups outside the repository, protect them as confidential records, and
verify them regularly by restoring only into a separate database.

### Restore verification

The restore script never drops, recreates, or writes to the active configured
database. First create a separate empty target database after confirming its
name is not the active `CHATBOT_DB_NAME`:

```bash
export CTRL4_MYSQL_DEFAULTS_FILE=/etc/ctrl4/mysql-client.cnf
mysql --defaults-extra-file="$CTRL4_MYSQL_DEFAULTS_FILE" \
  -e 'CREATE DATABASE ctrl4_restore_check CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'

CTRL4_RESTORE_DB_NAME=ctrl4_restore_check \
  ./backend/scripts/restore_database.sh \
  /secure/ctrl4-backups/ctrl4_YYYYMMDD_HHMMSS.sql
```

Inspect the restored database before any separately approved recovery action.

## AI runtime asset provisioning

### English emotion model

The released English emotion-model weight is a controlled artifact, not an
ordinary Git file. Obtain only the approved release file from the project
release custodian; do not use historical checkpoints or a different model.

| Item | Required value |
| --- | --- |
| Artifact filename | `ctrl4-eerm-english-latest-model.safetensors` |
| Destination | `ai_engine/models/english/latest/model.safetensors` |
| Expected size | `267841796` bytes |
| SHA-256 | `d90161c6b064d42ecee866e099f9f3125abb969e7a5ce76cd4c4fb32369ccce9` |

Copy the artifact through a protected operator-controlled channel, then verify
the complete runtime model directory before startup:

```bash
cd /path/to/CTRL4_Chatbot
./backend/.venv/bin/python backend/scripts/verify_emotion_model.py
```

The verifier checks the weight, model configuration, and tokenizer files
against `runtime_artifact_manifest.json`. A missing or mismatched artifact is a
deployment failure; CTRL4 does not fall back to another emotion model.

### RAG index

Place approved knowledge records in the configured RAG document directory and
build the index before normal production startup:

```bash
cd backend
../.venv/bin/python scripts/ingest_guidance_docs.py
```

Keep the generated index in protected deployment storage. Do not rebuild it on
each production start unless that work is intentionally scheduled. The build
stores `manifest.json` beside the FAISS index. It fingerprints the current
source files and RAG settings. If the fingerprint differs at startup, CTRL4
rebuilds only when `CHATBOT_RAG_AUTO_BUILD_ON_START=true`; otherwise it marks
the index stale and does not use it. The first manifest build preserves a
pre-manifest legacy index under the index directory's non-runtime `archive/`
folder for inspection.

## Starting the application

### Development

```bash
cd backend
../.venv/bin/python app.py
```

The development server listens on `http://127.0.0.1:5001` by default.

### Temporary Tailscale demonstration (no code or `.env` changes)

For a private demonstration, leave `backend/.env` unchanged and export runtime
overrides only in the terminal that starts Flask. They take precedence for that
one process and disappear when the terminal session ends.

With Tailscale connected on the demo host, bind directly to its Tailscale IPv4
address:

```bash
cd backend
export CTRL4_HOST="$(tailscale ip -4)"
export CTRL4_PORT=5001
../.venv/bin/python app.py
```

The command `tailscale ip -4` prints the address to share with authorized
demonstrators. They can open `http://TAILSCALE_IP:5001` from a device that is
permitted in the same tailnet. Verify the private demonstration from such a
device without submitting protected content:

```bash
curl --fail --silent --show-error http://TAILSCALE_IP:5001/health
```

If a local-network demonstration specifically requires all interfaces, use
`export CTRL4_HOST=0.0.0.0` instead. This broader binding can expose the app on
the host's LAN as well as Tailscale, so it requires an appropriate local
firewall and trusted network. Do not use Tailscale Funnel, port forwarding, or
another public-internet exposure method for CTRL4: the system handles student
and case information. End the session with `Ctrl+C`, then run
`unset CTRL4_HOST CTRL4_PORT` before a normal local start in the same terminal.

This demonstration path is not the supported production topology. Production
still requires the single-worker Gunicorn and HTTPS reverse-proxy arrangement
described below.

### Production

After explicit database preparation, run exactly one Gunicorn worker:

```bash
cd backend
../.venv/bin/gunicorn \
  --bind 127.0.0.1:5001 \
  --workers 1 \
  --access-logfile - \
  --error-logfile - \
  app:app
```

The reverse proxy should forward HTTPS traffic to this local listener. Do not
expose the Gunicorn listener directly to the public network.

## GitHub Actions production deployment

The repository includes `.github/workflows/deploy-production.yml`. It deploys
each push to `main` only after a secure SSH connection to the single production
host is configured. The workflow pulls source updates, installs any changed
dependencies, verifies the controlled emotion-model artifact, restarts the
single-worker `ctrl4` service, and checks local `/health`.

It deliberately does **not** copy or recreate `backend/.env`, the MySQL
database, the controlled model artifact, or generated RAG files. Those are
protected server-side operational assets. Before pulling source updates, the
workflow saves the generated RAG index files locally and restores them after
the pull so a repository cleanup cannot remove the provisioned production
index.

Create a dedicated GitHub Actions SSH key; do not reuse the server-to-GitHub
read-only repository deploy key. Add its public key to the production
application user's `~/.ssh/authorized_keys`, and add these GitHub repository
secrets:

| Secret | Value |
| --- | --- |
| `CTRL4_DEPLOY_HOST` | Production VPS hostname or IP address |
| `CTRL4_DEPLOY_USER` | Production application user (for example, `ctrl4`) |
| `CTRL4_DEPLOY_SSH_KEY` | Dedicated GitHub Actions private SSH key |
| `CTRL4_DEPLOY_KNOWN_HOSTS` | The exact production host entry from `ssh-keyscan -H HOST` verified by the operator |

Grant the application user passwordless permission only to restart and inspect
the `ctrl4` service; do not grant unrestricted sudo. Before relying on
automatic deployment, push a documentation-only change and confirm the Actions
run ends with the healthy `/health` response.

## Deferred MK III work

The saved `mkiii_startup_hardening_unvalidated.patch` is not part of the
release and must not be applied as a validated migration/startup solution.
Before a production deployment, validate a versioned migration strategy,
consider the deferred indexes, complete environment-specific security hardening,
and treat generated RAG artifacts as protected operational assets.

## Health and startup verification

After starting the application, verify the registered services without
authenticating or submitting private data:

```bash
curl --fail --silent --show-error http://127.0.0.1:5001/health
```

The expected response is HTTP 200 with the established success envelope. Also
confirm the session directory and log directory are owned by the application
user and are not web-accessible.

## Logging

Application logs default to `backend/data/logs/ctrl4.log` in development. Use
an absolute protected `CHATBOT_LOG_FILE` in production. Logs rotate at 5 MiB by
default and retain five previous files; configure the size/count values in
`backend/.env` to match host storage policy.

Deployment logging is aggregate-only. It must never include credentials, email
addresses, session values, conversation content, prompts, generated replies,
counselor notes, summaries, or secrets.

## Deployment checklist

- [ ] Install dependencies from root `requirements.txt` in a clean virtual environment.
- [ ] Create and protect `backend/.env`.
- [ ] Configure the single-instance CacheLib session directory.
- [ ] Prepare the database using the correct fresh or upgrade procedure.
- [ ] Verify a backup and a restore into a separate database.
- [ ] Provision the RAG index and selected LLM provider.
- [ ] Start one Gunicorn worker behind HTTPS.
- [ ] Confirm `GET /health` returns HTTP 200.
- [ ] Review protected log and session directory permissions.
