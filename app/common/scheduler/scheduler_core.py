import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib import import_module
from pkgutil import walk_packages

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import app as app_package
from app.common.scheduler.task_registry import get_registered_tasks

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """실행 중인 스케줄러 인스턴스를 반환한다."""
    if _scheduler is None:
        raise RuntimeError("Scheduler not initialized")
    return _scheduler


def _discover_task_modules() -> list[str]:
    """app/ 아래의 모든 tasks.py 모듈을 찾는다."""
    modules: list[str] = []
    for module_info in sorted(
        walk_packages(app_package.__path__, prefix=f"{app_package.__name__}."),
        key=lambda item: item.name,
    ):
        if module_info.name.rsplit(".", maxsplit=1)[-1] == "tasks":
            modules.append(module_info.name)
    return modules


def _import_all_task_modules() -> None:
    """모든 tasks.py 모듈을 import해서 데코레이터가 실행되도록 한다."""
    for module_name in _discover_task_modules():
        logger.info("Importing scheduled task module: %s", module_name)
        import_module(module_name)


@asynccontextmanager
async def scheduler_lifespan(app: object) -> AsyncGenerator[None, None]:
    """FastAPI lifespan에서 스케줄러를 시작하고 종료하는 컨텍스트 매니저."""
    global _scheduler  # noqa: PLW0603
    _scheduler = AsyncIOScheduler()

    _import_all_task_modules()

    for task_def in get_registered_tasks():
        _scheduler.add_job(
            task_def.func,
            trigger=task_def.trigger,
            id=task_def.job_id,
            name=task_def.name,
            **task_def.kwargs,
        )
        logger.info("Registered job: %s [%s]", task_def.job_id, task_def.trigger)

    _scheduler.start()
    logger.info("Scheduler started with %d job(s)", len(_scheduler.get_jobs()))

    try:
        yield
    finally:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler shut down")
