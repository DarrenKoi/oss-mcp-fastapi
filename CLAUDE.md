# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Internal FastAPI server for a semiconductor company. Serves web applications and background tasks for office users who need to interact with fab (fabrication) tools. The server is only accessible within the company network — no external/outbound access.

## Commands

```bash
# Setup
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run dev server
uvicorn app.main:app --reload

# Production (company-configured gunicorn/uvicorn)
gunicorn app.main:app -k uvicorn.workers.UvicornWorker
```

## Architecture

- **Entrypoint**: `app/main.py` — creates the FastAPI app, registers all routers with `/v1` prefix
- **Modules live under `app/common/`** — each module has its own subdirectory with a `router.py` for API endpoints

### Module pattern (two-class design)

Each module follows a server + client pattern:
- `*_server.py` — runs inside the FastAPI server, does the actual work (e.g., connects to FTP)
- `*_client.py` — Python SDK distributed to office users' local PCs, wraps HTTP calls to the server API via `httpx`
- `router.py` — FastAPI endpoints that instantiate the server class

### API versioning

All API routes are prefixed with `/v1` at the `include_router()` level in `main.py`. Individual routers define their own sub-prefix (e.g., `/ftp-proxy`), resulting in paths like `/v1/ftp-proxy/list`.

## Journals

Development journals are kept in `doc/journals/` in Korean. Use the `/journal` skill to generate session journals.

## Commit Automation Policy

When code is generated or edited in this repository, commit and push automatically only after a relevant verification step succeeds. Acceptable verification includes passing tests, a successful local startup check, or another concrete validation that matches the change. If verification cannot be run or fails, do not auto-push; report the blocker instead.
