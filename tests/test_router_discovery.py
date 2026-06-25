import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Match

from app.main import app, discover_router_module_names, discover_routers, is_router_module
from test_support.manual_router_case import sample_app


def test_is_router_module_accepts_router_prefix() -> None:
    assert is_router_module("app.oss.router")
    assert is_router_module("app.oss.router_v1")
    assert is_router_module("app.oss.router_v2")
    assert not is_router_module("app.oss.v1")


def test_discover_router_module_names_supports_manual_modules() -> None:
    module_names = discover_router_module_names(
        package_paths=sample_app.__path__,
        package_name=sample_app.__name__,
        manual_router_modules=(
            "test_support.manual_router_case.sample_app.custom_manual_routes",
        ),
    )

    assert module_names == [
        "test_support.manual_router_case.sample_app.custom_manual_routes",
        "test_support.manual_router_case.sample_app.router_alpha",
    ]


def test_discover_routers_merges_auto_and_manual_modules() -> None:
    routers = discover_routers(
        package_paths=sample_app.__path__,
        package_name=sample_app.__name__,
        manual_router_modules=(
            "test_support.manual_router_case.sample_app.custom_manual_routes",
        ),
    )

    test_app = FastAPI()
    for router in routers:
        test_app.include_router(router)

    client = TestClient(test_app)

    assert client.get("/sample/auto").json() == {"mode": "auto"}
    assert client.get("/sample/manual").json() == {"mode": "manual"}


def test_app_boots_and_health_ok() -> None:
    # 앱이 import 부작용으로 라우터를 등록하는 구조라, 단순히 import + /health 가
    # 떠 있으면 부팅 자체는 정상이라고 본다.
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}


def _route_resolves(method: str, path: str) -> bool:
    # 핸들러를 실제로 호출하지 않고(부작용 없이) "이 경로가 앱에 라우팅되는가"만 확인한다.
    # include_router 로 합쳐진 하위 라우터는 FastAPI 버전에 따라 app.routes 에
    # 평평하게 펼쳐지지 않으므로, 경로 문자열 매칭 대신 Starlette 의 라우팅 매칭을 쓴다.
    scope = {"type": "http", "method": method, "path": path}
    return any(route.matches(scope)[0] == Match.FULL for route in app.routes)


def test_every_discovered_router_is_mounted() -> None:
    # 자동 발견된 라우터가 전부 실제로 앱에 마운트돼 라우팅되는지 검사한다.
    # 새 router*.py 를 추가하면 자동으로 함께 검사되므로, 라우터를 더할 때마다
    # 이 테스트를 손볼 필요가 없다. (특정 prefix 나 /health 규칙을 강요하지 않는다.)
    routers = discover_routers()
    assert routers, "자동 발견된 라우터가 하나도 없다 — discovery 가 깨졌다"

    unresolved: list[str] = []
    for router in routers:
        for route in router.routes:
            methods = route.methods or {"GET"}
            method = "GET" if "GET" in methods else sorted(methods)[0]
            # 경로 파라미터({emp_no} 등)는 더미 값으로 치환해 매칭만 확인한다.
            probe = re.sub(r"{[^}]+}", "x", route.path)
            if not _route_resolves(method, probe):
                unresolved.append(f"{method} {route.path}")

    assert not unresolved, f"앱에 마운트되지 않은 라우트: {unresolved}"
