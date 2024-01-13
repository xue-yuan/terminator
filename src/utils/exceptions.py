from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from constants.error import ServerError


class CustomException(HTTPException):
    def __init__(self, status_code: int, error_code: int):
        self.status_code = status_code
        self.error_code = error_code


class BadRequestException(CustomException):
    def __init__(self, error_code: int):
        super().__init__(
            status_code=HTTP_400_BAD_REQUEST,
            error_code=error_code,
        )


class UnauthorizedException(CustomException):
    def __init__(self, error_code: int):
        super().__init__(
            status_code=HTTP_401_UNAUTHORIZED,
            error_code=error_code,
        )


class ForbiddenException(CustomException):
    def __init__(self, error_code: int):
        super().__init__(
            status_code=HTTP_403_FORBIDDEN,
            error_code=error_code,
        )


class ServerException(CustomException):
    def __init__(self, error_code: int):
        super().__init__(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            error_code=error_code,
        )


async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error_code": ServerError.UNDOCUMENTED_EXCEPTION},
    )


async def custom_exception_handler(request, exc: CustomException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code}
    )


async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": ServerError.UNDOCUMENTED_EXCEPTION},
    )
