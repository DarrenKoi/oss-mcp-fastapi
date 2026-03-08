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

- **Entrypoint**: `app/main.py` — creates the FastAPI app, auto-discovers every `router*` module under `app/`, and can also include explicitly listed modules from `MANUAL_ROUTER_MODULES`
- **Service packages live under `app/`** — each package can expose `router.py` for unversioned routes and `router_v1.py`, `router_v2.py`, and similar modules for versioned routes

### Module pattern (two-class design)

Each module follows a server + client pattern:
- `*_server.py` — runs inside the FastAPI server, does the actual work (e.g., connects to FTP)
- `*_client.py` — Python SDK distributed to office users' local PCs, wraps HTTP calls to the server API via `httpx`
- `router.py` — optional unversioned FastAPI endpoints for a package
- `router_v1.py`, `router_v2.py` — version-specific FastAPI endpoints that instantiate the server class and own their full URL prefixes
- `MANUAL_ROUTER_MODULES` in `app/main.py` — escape hatch for explicitly mounting router modules that do not follow the `router*` filename rule

### API versioning

API versioning uses suffix-style paths owned directly by each versioned router module. For example, a service package may expose `/oss/mtc/v1/...` from `router_v1.py` and later add `/oss/mtc/v2/...` from `router_v2.py`.

## Journals

Development journals are kept in `doc/journals/` in Korean. Use the `/journal` skill to generate session journals.

## Commit Automation Policy

When code is generated or edited in this repository, commit and push automatically only after a relevant verification step succeeds. Acceptable verification includes passing tests, a successful local startup check, or another concrete validation that matches the change. If verification cannot be run or fails, do not auto-push; report the blocker instead.
