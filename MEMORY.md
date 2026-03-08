# Project Memory

## Routing Architecture
- `app/main.py` auto-discovers every module whose filename starts with `router` under `app/` and mounts it directly.
- Versioned endpoints live in files such as `router_v1.py` and `router_v2.py`, and each router module owns its full path prefix.
- `app/main.py` also supports a `MANUAL_ROUTER_MODULES` list for exceptional router modules that must be mounted explicitly.
- API versioning uses suffix-style URLs such as `/oss/mtc/v1/...` and `/ftp-proxy/v1/...`.

## Service Layout
- Top-level service packages currently include `app/oss/`, `app/mcp/`, and `app/skewnono/`.
- `app/oss/` is subdivided into independently owned subpackages: `app/oss/mtc/`, `app/oss/aps/`, and `app/oss/dec/`.

## Client Compatibility
- `app/common/ftp_proxy/ftp_proxy_client.py` must follow the suffix-versioned server routes under `/ftp-proxy/v1/...`.
