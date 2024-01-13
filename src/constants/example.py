from pydantic import BaseModel


class ErrorCode(BaseModel):
    error_code: int = 10000


EXAMPLE_VALUE = {"model": ErrorCode}
EXAMPLE_RESPONSES = {
    400: EXAMPLE_VALUE,
    500: EXAMPLE_VALUE,
}

AUTH_EXAMPLE_RESPONSES = {
    401: EXAMPLE_VALUE,
    403: EXAMPLE_VALUE,
    **EXAMPLE_RESPONSES,
}

EMPTY_EXAMPLE_RESPONSES = {
    204: {},
}
