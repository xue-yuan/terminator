from fastapi import APIRouter

from controllers.api.auth import router_with_auth as auth_router_with_auth
from controllers.api.auth import router as auth_router
from controllers.api.user import router_with_auth as user_router_with_auth
from controllers.api.user import router as user_router
from controllers.api.exercise import router_with_auth as exercise_router_with_auth
from controllers.api.exercise_type import router_with_auth as exercise_type_router_with_auth
from controllers.api.workout import router_with_auth as workout_router_with_auth
from constants.example import AUTH_EXAMPLE_RESPONSES, EXAMPLE_RESPONSES


router = APIRouter(responses=EXAMPLE_RESPONSES)
router_with_auth = APIRouter(responses=AUTH_EXAMPLE_RESPONSES)

router.include_router(auth_router)
router.include_router(user_router)

router_with_auth.include_router(auth_router_with_auth)
router_with_auth.include_router(user_router_with_auth)
router_with_auth.include_router(exercise_router_with_auth)
router_with_auth.include_router(exercise_type_router_with_auth)
router_with_auth.include_router(workout_router_with_auth)

root = APIRouter(prefix="/api")
root.include_router(router)
root.include_router(router_with_auth)
