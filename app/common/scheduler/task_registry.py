from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_REGISTERED_TASKS: list["TaskDefinition"] = []


@dataclass(frozen=True)
class TaskDefinition:
    func: Callable
    trigger: str  # "cron", "interval", "date"
    kwargs: dict[str, Any] = field(default_factory=dict)
    job_id: str | None = None
    name: str | None = None


def scheduled_task(
    trigger: str,
    *,
    job_id: str | None = None,
    name: str | None = None,
    **trigger_kwargs: Any,
) -> Callable:
    """함수를 스케줄러 작업으로 등록하는 데코레이터.

    사용법:
        @scheduled_task("interval", minutes=5, job_id="ftp-health")
        async def check_ftp_health():
            ...

        @scheduled_task("cron", hour=2, minute=0, job_id="nightly-sync")
        async def nightly_data_sync():
            ...
    """

    def decorator(func: Callable) -> Callable:
        _REGISTERED_TASKS.append(
            TaskDefinition(
                func=func,
                trigger=trigger,
                kwargs=trigger_kwargs,
                job_id=job_id or f"{func.__module__}.{func.__qualname__}",
                name=name or func.__qualname__,
            ),
        )
        return func

    return decorator


def get_registered_tasks() -> list[TaskDefinition]:
    return list(_REGISTERED_TASKS)
