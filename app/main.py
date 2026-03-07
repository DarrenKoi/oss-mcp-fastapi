from importlib import import_module
from pkgutil import walk_packages

from fastapi import APIRouter, FastAPI

import app as app_package


def discover_routers() -> list[APIRouter]:
    routers: list[APIRouter] = []

    # Load every app.*.router module so new service packages are mounted automatically.
    for module_info in sorted(
        walk_packages(app_package.__path__, prefix=f"{app_package.__name__}."),
        key=lambda item: item.name,
    ):
        if not module_info.name.endswith(".router"):
            continue

        module = import_module(module_info.name)
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            routers.append(router)

    return routers


app = FastAPI(title="Internal MCP FastAPI Server")

for router in discover_routers():
    app.include_router(router, prefix="/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
