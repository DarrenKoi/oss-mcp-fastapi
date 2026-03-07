# Repository Guidelines

## Project Structure & Module Organization
`app/` contains the FastAPI application. The entrypoint is `app/main.py`, which auto-discovers every module whose filename starts with `router` under `app/` and mounts its exported `router` directly. Use `router.py` for unversioned routes and `router_v1.py`, `router_v2.py`, and similar files for versioned endpoints, with each router owning its full prefix such as `/oss/mtc/v1`. Shared FTP logic lives in `app/common/ftp_proxy/`, split between the API router, server-side FTP adapter, and a small client SDK. `run.py` is the local development launcher. `requirements.txt` pins the runtime dependencies. `doc/journals/` stores session notes and should not contain source code.

## Build, Test, and Development Commands
Create and activate a local environment before working:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run locally with the repo entrypoint:

```bash
python run.py
```

For auto-reload during development:

```bash
RELOAD=true python run.py
```

Direct ASGI startup is also acceptable:

```bash
uvicorn app.main:app --reload
```

## Coding Style & Naming Conventions
Use Python 3 with 4-space indentation and type hints for public functions. Follow PEP 8 naming: `snake_case` for modules, functions, and variables; `PascalCase` for classes. Keep routers thin and put FTP or transport logic into dedicated service classes such as `FTPProxyServer`. Name route modules with a `router` prefix so discovery can load them automatically, and let each router module declare the full path prefix it serves. Prefer small, explicit functions over shared magic configuration.

## Testing Guidelines
There is no automated test suite yet. Until one is added, verify changes manually by starting the app and checking endpoints such as `GET /health` and versioned routes like `/ftp-proxy/v1/*`, `/oss/v1/*`, or `/oss/mtc/v1/*`. When adding tests, use `pytest`, place them under `tests/`, and name files `test_<feature>.py`.

## Commit & Pull Request Guidelines
Recent commits use short, imperative summaries such as `Initial project setup with FTP proxy module` and `Refactor FTP proxy into server class and client SDK`. Keep commit messages focused on one change. Pull requests should include a brief purpose statement, impacted routes or modules, manual test notes, and sample requests or screenshots when API behavior changes.

When code is created or modified by the agent, commit and push automatically only after a relevant verification step succeeds. Use the smallest reasonable verification for the change, such as a passing test run, a successful app startup check, or a validated endpoint response. If verification is blocked or fails, stop before pushing and report the reason.

## Security & Configuration Tips
Do not commit `.env`, FTP credentials, or office hostnames. Prefer environment variables for local overrides such as `HOST`, `PORT`, `RELOAD`, and `LOG_LEVEL`. Treat FTP access as sensitive and avoid logging passwords or remote file contents.
