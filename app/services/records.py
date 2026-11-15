"""Personal records (PRs) of logged sets.

A working set is a PR when it beats every earlier working set of the same
exercise (earlier workouts, and earlier sets of the same workout):

- "weight": the heaviest weight (compared in kg)
- "e1rm":   the highest estimated 1RM (Epley; sets of 1-12 reps)
- "reps":   the most reps of a bodyweight set (weight 0)

Nothing is a PR in the first workout an exercise is done in: there is nothing
to beat yet (its sets only set the bar).
The frontend applies the same rules to sets that haven't been synced yet
(frontend/src/lib/records.js).
"""

from collections.abc import Iterable, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workout import Workout, WorkoutSet
from app.services.exercise import KG_PER_LB

# The kg factor is written into the SQL: as a bind parameter next to `ELSE 1`
# Postgres would type it as an integer and silently turn it into 0.
_PR_FLAGS = text(f"""
WITH sets AS (
    SELECT s.id, i.exercise_id, s.reps,
           s.weight * CASE WHEN i.weight_unit = 'lb' THEN {KG_PER_LB} ELSE 1.0 END AS kg,
           w.performed_at, w.id AS workout_id, i."order" AS item_order, s."order" AS set_order
    FROM workout_sets s
    JOIN workout_items i ON i.id = s.item_id
    JOIN workouts w ON w.id = i.workout_id
    WHERE w.user_id = :user_id AND i.exercise_id IN :exercise_ids AND s.kind = 'working' AND s.reps > 0
), scored AS (
    SELECT *, CASE WHEN reps = 1 THEN kg ELSE kg * (1 + reps / 30.0) END AS e1rm FROM sets
), compared AS (
    SELECT id, kg, reps, e1rm,
           workout_id <> first_value(workout_id) OVER (
               PARTITION BY exercise_id ORDER BY performed_at, workout_id
           ) AS done_before,
           max(kg) FILTER (WHERE kg > 0) OVER earlier AS best_kg,
           max(e1rm) FILTER (WHERE kg > 0 AND reps <= 12) OVER earlier AS best_e1rm,
           max(reps) FILTER (WHERE kg = 0) OVER earlier AS best_reps
    FROM scored
    WINDOW earlier AS (
        PARTITION BY exercise_id ORDER BY performed_at, workout_id, item_order, set_order
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
)
SELECT id,
       coalesce(done_before AND kg > 0 AND kg > best_kg, false) AS weight,
       coalesce(done_before AND kg > 0 AND reps <= 12 AND e1rm > best_e1rm, false) AS e1rm,
       coalesce(done_before AND kg = 0 AND reps > best_reps, false) AS reps
FROM compared
WHERE id IN :set_ids
""").bindparams(bindparam("exercise_ids", expanding=True), bindparam("set_ids", expanding=True))


async def mark_prs(db: AsyncSession, user_id: int, workouts: Iterable[Workout]) -> None:
    """Set `pr` (a list of "weight" / "e1rm" / "reps") on every set of these
    workouts. It's a plain attribute for the response, not stored: whether a
    set is a PR depends on the history before it, which can still change."""
    sets: Sequence[WorkoutSet] = [s for w in workouts for item in w.items for s in item.sets]
    for s in sets:
        s.pr = []
    if not sets:
        return
    exercise_ids = list({item.exercise_id for w in workouts for item in w.items})
    rows = await db.execute(
        _PR_FLAGS,
        {"user_id": user_id, "exercise_ids": exercise_ids, "set_ids": [s.id for s in sets]},
    )
    by_id = {s.id: s for s in sets}
    for row in rows:
        by_id[row.id].pr = [kind for kind in ("weight", "e1rm", "reps") if getattr(row, kind)]
