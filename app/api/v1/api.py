from fastapi import APIRouter

from app.api.v1.endpoints import (
    access,
    auth,
    backup,
    body_weights,
    catalog,
    community,
    exercises,
    plans,
    progress,
    recap,
    spotify,
    sync,
    workouts,
)

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(workouts.router, tags=["workouts"])
api_router.include_router(exercises.router, prefix="/exercises", tags=["exercises"])
api_router.include_router(plans.router, prefix="/plans", tags=["plans"])
api_router.include_router(body_weights.router, prefix="/body-weights", tags=["body weight"])
api_router.include_router(backup.router, tags=["backup"])
api_router.include_router(spotify.router, prefix="/spotify", tags=["spotify"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["exercise library"])
api_router.include_router(access.router, prefix="/admin/access", tags=["admin"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(progress.router, prefix="/progress", tags=["progress"])
api_router.include_router(recap.router, prefix="/recap", tags=["progress"])
api_router.include_router(community.router, prefix="/community", tags=["community"])
