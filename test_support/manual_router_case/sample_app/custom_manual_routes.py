from fastapi import APIRouter

router = APIRouter(prefix="/sample", tags=["Sample Manual"])


@router.get("/manual")
def manual_route() -> dict[str, str]:
    return {"mode": "manual"}
