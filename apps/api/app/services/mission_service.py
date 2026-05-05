"""Mission service – progress tracking, completion, reward claiming."""
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mission import MissionDefinition, UserMission
from app.services.ftk_service import FtkService


class MissionService:
    def __init__(self, db: AsyncSession, ftk_service: FtkService) -> None:
        self._db = db
        self._ftk = ftk_service

    async def get_user_missions(
        self, user_id: str, mission_type: str | None = None
    ) -> list[UserMission]:
        q = select(UserMission).where(UserMission.user_id == uuid.UUID(user_id))
        if mission_type:
            q = q.join(MissionDefinition).where(
                MissionDefinition.mission_type == mission_type
            )
        result = await self._db.execute(q)
        return list(result.scalars().all())

    async def increment_progress(
        self,
        user_id: str,
        mission_def_id: str,
        increment: int = 1,
    ) -> UserMission:
        uid = uuid.UUID(user_id)
        mid = uuid.UUID(mission_def_id)

        # Upsert mission progress
        result = await self._db.execute(
            select(UserMission).where(
                UserMission.user_id == uid,
                UserMission.mission_def_id == mid,
            )
        )
        user_mission = result.scalar_one_or_none()

        mission_def = await self._db.get(MissionDefinition, mid)
        if mission_def is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Mission not found")

        if user_mission is None:
            user_mission = UserMission(
                user_id=uid,
                mission_def_id=mid,
                progress=0,
            )
            self._db.add(user_mission)

        if user_mission.is_completed:
            return user_mission  # already done, no-op

        user_mission.progress = min(
            user_mission.progress + increment, mission_def.target_value
        )

        if user_mission.progress >= mission_def.target_value:
            user_mission.is_completed = True
            user_mission.completed_at = datetime.now(UTC)

        await self._db.flush()
        return user_mission

    async def claim_reward(
        self, user_id: str, user_mission_id: str
    ) -> tuple[UserMission, bool, int | None]:
        """Returns (user_mission, leveled_up, new_level)."""
        um = await self._db.get(UserMission, uuid.UUID(user_mission_id))
        if um is None or str(um.user_id) != user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Mission not found")
        if not um.is_completed:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Mission not yet completed"
            )
        if um.reward_claimed:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Reward already claimed"
            )

        mission_def = await self._db.get(MissionDefinition, um.mission_def_id)
        assert mission_def is not None

        um.reward_claimed = True

        # Grant FTK
        if mission_def.reward_ftk > 0:
            await self._ftk.credit(
                user_id=user_id,
                amount=mission_def.reward_ftk,
                tx_type="reward",
                reference_id=str(um.id),
                reference_type="mission",
            )

        # Grant EXP and check level-up
        leveled_up = False
        new_level: int | None = None
        if mission_def.reward_exp > 0:
            _, leveled_up, new_level = await self._ftk.add_exp(
                user_id=user_id, exp=mission_def.reward_exp
            )

        await self._db.flush()
        return um, leveled_up, new_level
