from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidToken, decode_token
from app.db.session import get_db
from app.models.user import User
from app.services.auth import AuthService
from app.services.backup import BackupService
from app.services.body_weight import BodyWeightService
from app.services.exercise import ExerciseService
from app.services.plan import PlanService
from app.services.spotify import SpotifyService
from app.services.summary import SummaryService
from app.services.workout import WorkoutService

DB = Annotated[AsyncSession, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)


def unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise unauthorized()
    try:
        user_id = decode_token(credentials.credentials, "access")
    except InvalidToken:
        raise unauthorized("Invalid or expired token") from None
    user = await AuthService(db).get_active_user(user_id)
    if user is None:
        raise unauthorized("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def _auth_service(db: DB) -> AuthService:
    return AuthService(db)


def _workout_service(db: DB) -> WorkoutService:
    return WorkoutService(db)


def _exercise_service(db: DB) -> ExerciseService:
    return ExerciseService(db)


def _plan_service(db: DB) -> PlanService:
    return PlanService(db)


def _summary_service(db: DB) -> SummaryService:
    return SummaryService(db)


def _body_weight_service(db: DB) -> BodyWeightService:
    return BodyWeightService(db)


def _backup_service(db: DB) -> BackupService:
    return BackupService(db)


def _spotify_service(db: DB) -> SpotifyService:
    return SpotifyService(db)


AuthSvc = Annotated[AuthService, Depends(_auth_service)]
WorkoutSvc = Annotated[WorkoutService, Depends(_workout_service)]
ExerciseSvc = Annotated[ExerciseService, Depends(_exercise_service)]
PlanSvc = Annotated[PlanService, Depends(_plan_service)]
SummarySvc = Annotated[SummaryService, Depends(_summary_service)]
BodyWeightSvc = Annotated[BodyWeightService, Depends(_body_weight_service)]
BackupSvc = Annotated[BackupService, Depends(_backup_service)]
SpotifySvc = Annotated[SpotifyService, Depends(_spotify_service)]
