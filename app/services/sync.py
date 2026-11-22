"""Fingerprints of a user's data, one per kind (GET /sync/state).

A client keeps the fingerprints it last saw and refetches only the kinds whose
fingerprint changed: coming back to the app costs one small request instead of
downloading everything again. Each fingerprint is built from cheap aggregates
(row count + latest update, or ids that change on every edit), so computing
them never loads the data itself.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.body_weight import BodyWeight
from app.models.exercise import Exercise
from app.models.plan import Plan, PlanDay, PlanExercise
from app.models.progress import AchievementUnlock
from app.models.spotify import SpotifyLink
from app.models.user import User
from app.models.workout import Workout
from app.services import achievements
from app.services.catalog import CatalogService


def _digest(*parts: object) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]


class SyncService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _count_and_latest(self, model, user_id: int) -> tuple:
        stmt = select(func.count(), func.max(model.updated_at)).where(model.user_id == user_id)
        return tuple((await self.db.execute(stmt)).one())

    async def _plans(self, user_id: int) -> tuple:
        # Plan fields and day names can change in place; a day's exercises are
        # rebuilt on every edit, so their highest id moves.
        plans = (
            await self.db.execute(
                select(Plan.id, Plan.name, Plan.description, Plan.is_public)
                .where(Plan.creator_id == user_id)
                .order_by(Plan.id)
            )
        ).all()
        days = (
            await self.db.execute(
                select(PlanDay.id, PlanDay.name, PlanDay.order)
                .join(Plan)
                .where(Plan.creator_id == user_id)
                .order_by(PlanDay.id)
            )
        ).all()
        exercises = (
            await self.db.execute(
                select(func.count(PlanExercise.id), func.max(PlanExercise.id))
                .join(PlanDay)
                .join(Plan)
                .where(Plan.creator_id == user_id)
            )
        ).one()
        return tuple(map(tuple, plans)), tuple(map(tuple, days)), tuple(exercises)

    async def state(self, user: User) -> dict[str, str]:
        workouts = await self._count_and_latest(Workout, user.id)
        exercises = await self._count_and_latest(Exercise, user.id)
        body_weights = await self._count_and_latest(BodyWeight, user.id)
        plans = await self._plans(user.id)
        catalog = await CatalogService(self.db).fingerprint()
        # Titles given by hand: no workout moves when one arrives, so it counts by itself.
        granted = await self.db.scalar(
            select(func.count()).where(
                AchievementUnlock.user_id == user.id, AchievementUnlock.achievement.in_(achievements.GRANTED)
            )
        )
        spotify = (
            await self.db.execute(select(SpotifyLink.updated_at).where(SpotifyLink.user_id == user.id))
        ).scalar_one_or_none()
        return {
            # Workouts show exercise names; exercises carry stats and records from workouts.
            "workouts": _digest(workouts, exercises),
            "exercises": _digest(exercises, workouts),
            # Dates and set counts of all workouts (the training calendar).
            "activity": _digest(workouts),
            "plans": _digest(plans, exercises),
            "body_weights": _digest(body_weights),
            # The exercise library is shared: the same for everyone.
            "catalog": _digest(catalog),
            "summary": _digest(workouts, plans, user.active_plan_id),
            # XP, levels and achievements come from workouts, weigh-ins and the muscle
            # groups of exercises (yours and the library's), the rules themselves, and titles given by hand.
            "progress": _digest(
                workouts, exercises, body_weights, catalog, user.title, achievements.VERSION, granted
            ),
            "spotify": _digest(bool(settings.SPOTIFY_CLIENT_ID), spotify),
            "user": _digest(user.email, user.full_name, user.active_plan_id, settings.is_admin(user.email)),
        }
