"""Who else trains here (GET /community): everyone who may use the app, with
their level and the titles they wear. Sorted by name, not by anything earned:
everyone trains for themselves here, nobody is ranked.

The feed says who finished a workout and when, nothing more: the rest of a
workout is private. A high-five on one is just a gesture; it earns nothing.
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.high_five import HighFive
from app.models.progress import AchievementUnlock
from app.models.user import User
from app.models.workout import Workout
from app.schemas.community import FeedItem, HighFiveIn, Player, TeamGoal
from app.schemas.progress import TitleOut
from app.services.access import members as access_members
from app.services.achievements import find_tier, level_for, title_key
from app.services.errors import Invalid, NotFound
from app.services.progress import xp_totals
from app.services.team import TeamService


class CommunityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def players(self, me: User) -> list[Player]:
        members = await access_members(self.db)
        if me.id not in {u.id for u in members}:
            members.append(me)
        ids = [u.id for u in members]
        xp = await xp_totals(self.db, ids)
        unlocked = set(
            (
                await self.db.execute(
                    select(AchievementUnlock.user_id, AchievementUnlock.achievement, AchievementUnlock.target).where(
                        AchievementUnlock.user_id.in_([u.id for u in members if u.title or u.community_title])
                    )
                )
            ).all()
        )
        def worn(user_id: int, key: str | None) -> TitleOut | None:
            found = find_tier(key) if key else None
            if not found or (user_id, found[0].id, found[1].target) not in unlocked:
                return None
            return TitleOut(key=title_key(*found), title=found[1].title, medal=found[1].medal)

        players = [
            Player(
                id=u.id,
                name=name_of(u),
                level=level_for(xp[u.id]),
                title=worn(u.id, u.title),
                community_title=worn(u.id, u.community_title),
                you=u.id == me.id,
            )
            for u in members
        ]
        return sorted(players, key=lambda p: (p.name.casefold(), p.id))

    async def goal(self, me: User) -> TeamGoal:
        week, weeks = await TeamService(self.db).this_week(me.id)
        reached = [w for w in weeks if w.reached and me.id in w.first]
        streak = 0
        for w in reversed(weeks):
            if w.reached and me.id in w.first:
                streak += 1
            elif w is not week:  # the week under way can still make it
                break
        return TeamGoal(
            week_start=week.start,
            week_end=week.start + timedelta(weeks=1),
            target=week.target,
            total=week.total,
            reached=week.reached,
            trained=sorted(week.first),
            weeks_reached=len(reached),
            streak=streak,
        )

    async def feed(self, me: User, before: datetime | None = None, limit: int = 30) -> list[FeedItem]:
        """Members' finished workouts, latest first: who and when."""
        people = {u.id: u for u in await access_members(self.db)}
        finished = Workout.performed_at + func.make_interval(0, 0, 0, 0, 0, 0, func.coalesce(Workout.duration_seconds, 0))
        stmt = (
            select(Workout.id, Workout.uuid, Workout.user_id, finished.label("at"))
            .where(Workout.user_id.in_(list(people)))
            .order_by(finished.desc(), Workout.id.desc())
            .limit(limit)
        )
        if before is not None:
            stmt = stmt.where(finished < before)
        rows = (await self.db.execute(stmt)).all()
        fives = (
            await self.db.execute(
                select(HighFive.workout_id, HighFive.user_id)
                .where(HighFive.workout_id.in_([r.id for r in rows]))
                .order_by(HighFive.created_at)
            )
        ).all()
        by_workout: dict[int, list[int]] = {}
        for workout_id, user_id in fives:
            by_workout.setdefault(workout_id, []).append(user_id)
        return [
            FeedItem(
                workout_id=r.uuid,
                player_id=r.user_id,
                name=name_of(people[r.user_id]),
                at=r.at,
                you=r.user_id == me.id,
                high_fived=me.id in by_workout.get(r.id, []),
                high_fivers=[name_of(people[u]) for u in by_workout.get(r.id, []) if u in people]
                if r.user_id == me.id
                else [],
            )
            for r in rows
        ]

    async def _members_workout(self, workout_uuid: UUID) -> Workout:
        workout = (await self.db.execute(select(Workout).where(Workout.uuid == workout_uuid))).scalar_one_or_none()
        if workout is None or workout.user_id not in {u.id for u in await access_members(self.db)}:
            raise NotFound
        return workout

    async def high_five(self, me: User, workout_uuid: UUID, on: bool = True) -> None:
        """High-five someone's workout (idempotent), or take it back."""
        workout = await self._members_workout(workout_uuid)
        if workout.user_id == me.id:
            raise Invalid("That's your own workout")
        if on:
            await self.db.execute(
                insert(HighFive).values(workout_id=workout.id, user_id=me.id).on_conflict_do_nothing()
            )
        else:
            await self.db.execute(
                HighFive.__table__.delete().where(HighFive.workout_id == workout.id, HighFive.user_id == me.id)
            )
        await self.db.commit()

    async def high_fives_for(self, me: User, since: datetime | None = None) -> list[HighFiveIn]:
        """High-fives on your workouts, latest first."""
        stmt = (
            select(User, Workout.uuid, Workout.performed_at, HighFive.created_at)
            .join(Workout, Workout.id == HighFive.workout_id)
            .join(User, User.id == HighFive.user_id)
            .where(Workout.user_id == me.id)
            .order_by(HighFive.created_at.desc())
            .limit(50)
        )
        if since is not None:
            stmt = stmt.where(HighFive.created_at > since)
        return [
            HighFiveIn(name=name_of(u), workout_id=w, workout_at=w_at, at=at)
            for u, w, w_at, at in (await self.db.execute(stmt)).all()
        ]


def name_of(user: User) -> str:
    return (user.full_name or "").strip() or "Player"
