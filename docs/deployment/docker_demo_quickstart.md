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

## Docker-only demonstration (no repository download)

The following macOS/Linux commands pull and run the complete demonstration
without cloning this repository or downloading `compose.demo.yaml`. Docker
downloads the CTRL4 application image and the official MySQL image itself.

```bash
export CHATBOT_GEMINI_API_KEY='paste-your-key-here'

docker network create ctrl4-demo-net
docker volume create ctrl4-demo-mysql

docker run -d --name ctrl4-demo-db \
  --network ctrl4-demo-net --network-alias ctrl4-demo-db \
  -e MYSQL_DATABASE=soc_chatbot_demo \
  -e MYSQL_USER=ctrl4_demo \
  -e MYSQL_PASSWORD=ctrl4-demo-only \
  -e MYSQL_ROOT_PASSWORD=local-demo-root-only \
  -v ctrl4-demo-mysql:/var/lib/mysql \
  mysql:8.4

docker run -d --name ctrl4-demo-app \
  --network ctrl4-demo-net \
  -p 127.0.0.1:5001:5001 \
  -e CHATBOT_GEMINI_API_KEY="$CHATBOT_GEMINI_API_KEY" \
  -v ctrl4-demo-sessions:/runtime/sessions \
  -v ctrl4-demo-logs:/runtime/logs \
  jabezapilado/ctrl4-chatbot-mkiii:demo
```

Wait up to a few minutes on the first run while MySQL initializes, then open
`http://localhost:5001`. To check readiness:

```bash
curl http://127.0.0.1:5001/health
```

To remove this Docker-only demo after presenting:

```bash
docker rm -f ctrl4-demo-app ctrl4-demo-db
docker network rm ctrl4-demo-net
docker volume rm ctrl4-demo-mysql ctrl4-demo-sessions ctrl4-demo-logs
```

The remainder of this guide provides the equivalent Docker Compose procedure,
which is shorter for repeat demonstrations.

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
