from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app, discover_routers, is_router_module


def test_is_router_module_accepts_router_prefix() -> None:
    assert is_router_module("app.oss.router")
    assert is_router_module("app.oss.router_v1")
    assert is_router_module("app.oss.router_v2")
    assert not is_router_module("app.oss.v1")


def test_discover_routers_loads_versioned_router_modules() -> None:
    prefixes = {router.prefix for router in discover_routers()}

    assert prefixes == {
        "/ftp-proxy/v1",
        "/mcp/v1",
        "/oss/aps/v1",
        "/oss/dec/v1",
        "/oss/mtc/v1",
        "/oss/v1",
        "/skewnono/v1",
    }


def test_app_exposes_health_and_versioned_routes() -> None:
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/oss/v1/health").json() == {
        "service": "oss",
        "version": "v1",
        "status": "ok",
    }
    assert client.get("/mcp/v1/health").json() == {
        "service": "mcp",
        "version": "v1",
        "status": "ok",
    }
    assert client.get("/oss/mtc/v1/health").json() == {
        "service": "oss",
        "module": "mtc",
        "version": "v1",
        "status": "ok",
    }

    paths = {
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
    }
    assert "/ftp-proxy/v1/list" in paths
