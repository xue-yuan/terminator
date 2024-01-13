# Terminator

## Prerequsite

1. postgresql >= 14

## Installation

1. `poetry install --no-root`
2. `cp config.py.example config.py`
3. fill username and password
4. uvicorn main:app --reload

## Structures

1. `src/utils/responses.py` defines custom responses.
2. `src/utils/exceptions.py` defines custom exceptions and exception handlers.
3. `src/constants/example.py` defines example values for Swagger.
4. `src/controllers/models.py` defines request/response models.

## Token Flow

Redis is used as a blacklist.

1. The client checks the expiration time before making a request. If the expiration time is less than 30 minutes, the client requests `/refresh_token` first.
2. `/refresh_token` will generate a new token. Additionally, it stores the old token into Redis for an hour.
3. The server checks whether the token is stored in Redis. If it did, the server returns a 403 error.
