from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_farms() -> list[dict]:
    return []


@router.get("/{farm_id}")
async def get_farm(farm_id: str) -> dict:
    return {"id": farm_id}
