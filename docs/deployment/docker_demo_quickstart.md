# CTRL4 Chatbot MK III Docker Demonstration Quick Start

This guide starts the self-contained, presentation-only CTRL4 demonstration
from Docker Hub. It uses an isolated MySQL container and fictitious demo
accounts. It does not use XAMPP, a local CTRL4 installation, a production
database, or real student data.

## Before you begin

Install and open [Docker Desktop](https://www.docker.com/products/docker-desktop/).
Wait for Docker Engine to show as running, then open Terminal (macOS/Linux) or
PowerShell (Windows).

You also need a Gemini API key for the demonstration. The key is entered only
on the presentation computer at runtime; it is not included in the GitHub
repository, Docker image, or Docker Hub.

## 1. Download the Compose file

Create a new folder for the demonstration and download the small Compose file:

```bash
mkdir ctrl4-docker-demo
cd ctrl4-docker-demo
curl -fsSLO https://raw.githubusercontent.com/jabezapilado/CTRL4_Chatbot_MKIII/dockerization/compose.demo.yaml
```

Alternatively, clone the Docker branch:

```bash
git clone -b dockerization https://github.com/jabezapilado/CTRL4_Chatbot_MKIII.git
cd CTRL4_Chatbot_MKIII
```

## 2. Provide the Gemini API key for this terminal session

**macOS/Linux**

```bash
export CHATBOT_GEMINI_API_KEY='paste-your-key-here'
```

**Windows PowerShell**

```powershell
$env:CHATBOT_GEMINI_API_KEY = 'paste-your-key-here'
```

Do not place the key in the Compose file or commit it to Git.

## 3. Pull and start the complete system

```bash
docker compose -f compose.demo.yaml pull
docker compose -f compose.demo.yaml up -d
```

Docker pulls two images automatically:

- `jabezapilado/ctrl4-chatbot-mkiii:demo` — CTRL4 application, approved demo
  model, and RAG retrieval data.
- `mysql:8.4` — isolated database initialized with fictitious accounts.

## 4. Confirm that the system is ready

```bash
docker compose -f compose.demo.yaml ps
```

The `app` and `db` services should show as running. Docker Desktop's
**Containers** page will show the same two services as `ctrl4-demo-app-1` and
`ctrl4-demo-db-1`.

Open the system in a browser:

```text
http://localhost:5001
```

## Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Student | `demo.student@ctrl4.local` | `DemoStudent2026!` |
| Guidance Staff | `demo.staff@ctrl4.local` | `DemoStaff2026!` |
| Administrator | `demo.admin@ctrl4.local` | `DemoAdmin2026!` |

These accounts are fictitious and exist only in the local Docker demo database.

## Stop, restart, or remove the demo

```bash
docker compose -f compose.demo.yaml stop     # stop the services
docker compose -f compose.demo.yaml start    # start them again
docker compose -f compose.demo.yaml down     # remove containers; retain demo data
docker compose -f compose.demo.yaml down -v  # remove containers and demo data
```

Use `down -v` only when you intentionally want to reset the demonstration
database.
