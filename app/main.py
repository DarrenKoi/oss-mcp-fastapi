from collections.abc import Iterable, Sequence
from importlib import import_module
from pkgutil import walk_packages

from fastapi import APIRouter, FastAPI

import app as app_package


MANUAL_ROUTER_MODULES: tuple[str, ...] = ()


def is_router_module(module_name: str) -> bool:
    return module_name.rsplit(".", maxsplit=1)[-1].startswith("router")


def discover_router_module_names(
    package_paths: Iterable[str] | None = None,
    package_name: str | None = None,
    manual_router_modules: Sequence[str] | None = None,
) -> list[str]:
    search_paths = app_package.__path__ if package_paths is None else package_paths
    search_package_name = app_package.__name__ if package_name is None else package_name
    module_names = set(MANUAL_ROUTER_MODULES if manual_router_modules is None else manual_router_modules)

    # Load every app.*.router* module so versioned routers can live in dedicated files.
    for module_info in sorted(
        walk_packages(search_paths, prefix=f"{search_package_name}."),
        key=lambda item: item.name,
    ):
        if not is_router_module(module_info.name):
            continue

        module_names.add(module_info.name)

    return sorted(module_names)


def load_router(module_name: str) -> APIRouter | None:
    module = import_module(module_name)
    router = getattr(module, "router", None)
    if isinstance(router, APIRouter):
        return router

    return None


def discover_routers(
    package_paths: Iterable[str] | None = None,
    package_name: str | None = None,
    manual_router_modules: Sequence[str] | None = None,
) -> list[APIRouter]:
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


app = FastAPI(title="Internal MCP FastAPI Server")

for router in discover_routers():
    app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
