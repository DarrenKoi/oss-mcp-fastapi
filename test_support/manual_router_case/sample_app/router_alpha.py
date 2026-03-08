from fastapi import APIRouter

router = APIRouter(prefix="/sample", tags=["Sample Auto"])


@router.get("/auto")
def auto_route() -> dict[str, str]:
    return {"mode": "auto"}
