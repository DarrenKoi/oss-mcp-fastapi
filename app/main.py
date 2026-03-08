# collections.abc의 Iterable, Sequence는 "이 값이 어떤 식으로 다뤄지는지"를 설명하는 타입 힌트다.
# - Iterable[str]: for 문으로 순회할 수 있는 문자열 묶음이면 된다. (예: list, tuple, generator)
# - Sequence[str]: 순서가 있는 문자열 목록이다. (예: list, tuple)
from collections.abc import Iterable, Sequence
from importlib import import_module
from pkgutil import walk_packages

from fastapi import APIRouter, FastAPI

import app as app_package


# 자동 규칙으로 찾을 수 없는 라우터 모듈이 있으면 여기에 dotted path를 수동 등록한다.
# 예:
# MANUAL_ROUTER_MODULES = (
#     "app.oss.custom_manual_routes",
#     "app.ftp_proxy.special_router_module",
# )
# 위 문자열은 "router 변수를 export하는 파이썬 모듈 경로"여야 한다.
MANUAL_ROUTER_MODULES: tuple[str, ...] = ()


def is_router_module(module_name: str) -> bool:
    # 모듈의 마지막 이름이 router로 시작하면 자동 등록 대상이라고 본다.
    return module_name.rsplit(".", maxsplit=1)[-1].startswith("router")


def discover_router_module_names(
    package_paths: Iterable[str] | None = None,
    package_name: str | None = None,
    manual_router_modules: Sequence[str] | None = None,
) -> list[str]:
    # 기본값으로 app 패키지 전체를 검색하되, 테스트에서는 다른 패키지를 주입할 수 있다.
    # package_paths는 "순회만 가능하면 되는" 입력이라 Iterable[str]로 받는다.
    search_paths = app_package.__path__ if package_paths is None else package_paths
    search_package_name = app_package.__name__ if package_name is None else package_name
    # manual_router_modules는 순서를 가진 모듈 경로 목록이라 Sequence[str]로 받는다.
    # 수동 등록 목록도 자동 탐색 결과와 함께 합쳐서 중복 없이 관리한다.
    module_names = set(MANUAL_ROUTER_MODULES if manual_router_modules is None else manual_router_modules)

    # app.* 아래의 router* 모듈을 모두 찾는다.
    # 그래서 router_v1, router_v2처럼 버전별 파일을 분리해도 자동으로 포함된다.
    for module_info in sorted(
        walk_packages(search_paths, prefix=f"{search_package_name}."),
        key=lambda item: item.name,
    ):
        if not is_router_module(module_info.name):
            continue

        module_names.add(module_info.name)

    # import 순서를 안정적으로 유지하려고 정렬된 목록을 반환한다.
    return sorted(module_names)


def load_router(module_name: str) -> APIRouter | None:
    # 문자열 모듈 경로를 실제 모듈로 import한 뒤, 그 안의 router 객체를 꺼낸다.
    module = import_module(module_name)
    router = getattr(module, "router", None)
    if isinstance(router, APIRouter):
        return router

    # router 변수가 없거나 APIRouter가 아니면 무시한다.
    return None


def discover_routers(
    package_paths: Iterable[str] | None = None,
    package_name: str | None = None,
    manual_router_modules: Sequence[str] | None = None,
) -> list[APIRouter]:
    # 최종적으로 FastAPI 앱에 include할 APIRouter 객체들을 모은다.
    routers: list[APIRouter] = []

    for module_name in discover_router_module_names(
        package_paths=package_paths,
        package_name=package_name,
        manual_router_modules=manual_router_modules,
    ):
        router = load_router(module_name)
        if router is not None:
            routers.append(router)

    return routers


# 앱 시작 시점에 FastAPI 인스턴스를 만들고,
# 자동 탐색된 모든 라우터를 즉시 등록한다.
app = FastAPI(title="Internal MCP FastAPI Server")

for router in discover_routers():
    app.include_router(router)


@app.get("/health")
def health():
    # 서버 기동 여부를 빠르게 확인하는 기본 헬스 체크 엔드포인트다.
    return {"status": "ok"}
