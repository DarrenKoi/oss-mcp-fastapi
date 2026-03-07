# Repository Guidelines

## Project Structure & Module Organization
`app/` contains the FastAPI application. The entrypoint is `app/main.py`, which mounts the FTP proxy router under `/v1`. Shared FTP logic lives in `app/common/ftp_proxy/`, split between the API router, server-side FTP adapter, and a small client SDK. `run.py` is the local development launcher. `requirements.txt` pins the runtime dependencies. `doc/journals/` stores session notes and should not contain source code.

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
Use Python 3 with 4-space indentation and type hints for public functions. Follow PEP 8 naming: `snake_case` for modules, functions, and variables; `PascalCase` for classes. Keep routers thin and put FTP or transport logic into dedicated service classes such as `FTPProxyServer`. Prefer small, explicit functions over shared magic configuration.

## Testing Guidelines
There is no automated test suite yet. Until one is added, verify changes manually by starting the app and checking endpoints such as `GET /health` and the `/v1/ftp-proxy/*` routes. When adding tests, use `pytest`, place them under `tests/`, and name files `test_<feature>.py`.

## Commit & Pull Request Guidelines
Recent commits use short, imperative summaries such as `Initial project setup with FTP proxy module` and `Refactor FTP proxy into server class and client SDK`. Keep commit messages focused on one change. Pull requests should include a brief purpose statement, impacted routes or modules, manual test notes, and sample requests or screenshots when API behavior changes.

## Security & Configuration Tips
Do not commit `.env`, FTP credentials, or office hostnames. Prefer environment variables for local overrides such as `HOST`, `PORT`, `RELOAD`, and `LOG_LEVEL`. Treat FTP access as sensitive and avoid logging passwords or remote file contents.
