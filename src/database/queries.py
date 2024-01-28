from sqlalchemy import text


def get_all_workouts(order):
    return text(
        f"""
        WITH ExerciseData AS (
            SELECT
                e.exercise_id,
                CASE
                    WHEN COUNT(s.repetition) > 0
                    THEN json_agg(
                        json_build_object(
                            'repetition', s.repetition,
                            'weight', s.weight
                        )
                    )
                    ELSE '[]'::json
                END AS sets
            FROM exercises e
            LEFT JOIN sets s ON e.exercise_id = s.exercise_id
            GROUP BY e.exercise_id
        ),
        WorkoutData AS (
            SELECT
                w.workout_id,
                w.datetime,
                CASE
                    WHEN COUNT(e.exercise_id) > 0
                    THEN json_agg(
                        json_build_object(
                            'exercise_id', e.exercise_id,
                            'exercise_type_id', e.exercise_type_id,
                            'sets', (SELECT sets FROM ExerciseData ed WHERE ed.exercise_id = e.exercise_id)
                        )
                    )
                    ELSE '[]'::json
                END AS exercises
            FROM workouts w
            LEFT JOIN exercises e ON w.workout_id = e.workout_id
            WHERE w.user_id = :user_id
            AND w.datetime BETWEEN :from_date AND :to_date
            GROUP BY w.workout_id, w.datetime
            ORDER BY w.datetime {order}
            LIMIT :limit OFFSET :offset
        ),
        TotalWorkouts AS (
            SELECT COUNT(DISTINCT workout_id) AS total
            FROM workouts AS w
            WHERE user_id = :user_id
            AND w.datetime BETWEEN :from_date AND :to_date
        )
        SELECT
            json_build_object(
                'total', (SELECT total FROM TotalWorkouts),
                'rows', json_agg(
                    json_build_object(
                        'workout_id', wd.workout_id,
                        'datetime', wd.datetime,
                        'exercises', wd.exercises
                    )
                )
            ) AS result
        FROM WorkoutData wd;
        """
    )
