from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_players() -> list[dict]:
    return []


@router.get("/{player_id}")
async def get_player(player_id: str) -> dict:
    return {"id": player_id}
