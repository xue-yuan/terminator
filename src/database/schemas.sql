CREATE TABLE users (
        id SERIAL NOT NULL,
        user_id VARCHAR(50) NOT NULL,
        username VARCHAR(31) NOT NULL,
        password VARCHAR(60) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        UNIQUE (user_id),
        UNIQUE (username)
)

CREATE TABLE exercises (
        id SERIAL NOT NULL,
        exercise_name VARCHAR(255) NOT NULL,
        PRIMARY KEY (id),
        UNIQUE (exercise_name)
)

CREATE TABLE workouts (
        id SERIAL NOT NULL,
        workout_id VARCHAR(50) NOT NULL,
        user_id VARCHAR(50),
        datetime TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (id),
        UNIQUE (workout_id),
        FOREIGN KEY(user_id) REFERENCES users (user_id)
)

CREATE TABLE records (
        id SERIAL NOT NULL,
        record_id VARCHAR(50) NOT NULL,
        workout_id VARCHAR(50),
        exercise_id INTEGER,
        PRIMARY KEY (id),
        UNIQUE (record_id),
        FOREIGN KEY(workout_id) REFERENCES workouts (workout_id),
        FOREIGN KEY(exercise_id) REFERENCES exercises (id)
)

CREATE TABLE sets (
        id SERIAL NOT NULL,
        set_id VARCHAR(50) NOT NULL,
        record_id VARCHAR(50),
        repetition SMALLINT,
        weight NUMERIC(5, 2),
        PRIMARY KEY (id),
        UNIQUE (set_id),
        FOREIGN KEY(record_id) REFERENCES records (record_id)
)
