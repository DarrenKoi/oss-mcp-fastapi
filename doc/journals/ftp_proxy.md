# FTP Proxy - Development Journal

## 2026-03-07: Initial Implementation

### What was done
- Created project scaffolding for the FastAPI server (`app/main.py`)
- Implemented bidirectional FTP proxy module under `app/common/ftp_proxy/`
- Created GitHub repo: https://github.com/DarrenKoi/oss-mcp-fastapi

### Structure
```
app/
├── main.py                        # FastAPI entrypoint, health check
└── common/
    └── ftp_proxy/
        ├── ftp_client.py          # FTP connection helper (stdlib ftplib)
        └── router.py              # API endpoints
```

### API Endpoints (v1)
| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/v1/ftp-proxy/list` | List files/directories on an FTP server |
| `GET`  | `/v1/ftp-proxy/download` | Stream-download a file from FTP to caller |
| `POST` | `/v1/ftp-proxy/upload` | Upload a file from caller to FTP server |

### Design Decisions
- **Protocol**: Standard FTP via `ftplib` (stdlib, no extra dependency)
- **Streaming**: Downloads use `StreamingResponse` — files are not staged on the server
- **Credentials**: Passed per-request (host, port, user, password) to support multiple fab tools
- **Direction**: Bidirectional — office users can both download from and upload to fab tools
- **Versioning**: All API routes are prefixed with `/v1`

### Environment
- Python 3.11, pip + venv
- FastAPI + uvicorn/gunicorn (company-configured)
- Internal only — no external access
