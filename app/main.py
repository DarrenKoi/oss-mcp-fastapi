from importlib import import_module
from pkgutil import walk_packages

from fastapi import APIRouter, FastAPI

import app as app_package


def is_router_module(module_name: str) -> bool:
    return module_name.rsplit(".", maxsplit=1)[-1].startswith("router")


def discover_routers() -> list[APIRouter]:
    routers: list[APIRouter] = []

    # Load every app.*.router* module so versioned routers can live in dedicated files.
    for module_info in sorted(
        walk_packages(app_package.__path__, prefix=f"{app_package.__name__}."),
        key=lambda item: item.name,
    ):
        if not is_router_module(module_info.name):
            continue

        module = import_module(module_info.name)
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            routers.append(router)

    return routers


app = FastAPI(title="Internal MCP FastAPI Server")

for router in discover_routers():
    app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
