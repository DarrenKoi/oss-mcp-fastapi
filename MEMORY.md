# Project Memory

## Routing Architecture
- `app/main.py` auto-discovers every `router.py` module under `app/` and mounts it directly.
- Package-level `router.py` files own the service prefix and aggregate version modules such as `v1.py` and `v2.py`.
- API versioning uses suffix-style URLs such as `/oss/mtc/v1/...` and `/ftp-proxy/v1/...`.

## Service Layout
- Top-level service packages currently include `app/oss/`, `app/mcp/`, and `app/skewnono/`.
- `app/oss/` is subdivided into independently owned subpackages: `app/oss/mtc/`, `app/oss/aps/`, and `app/oss/dec/`.

## Client Compatibility
- `app/common/ftp_proxy/ftp_proxy_client.py` must follow the suffix-versioned server routes under `/ftp-proxy/v1/...`.
