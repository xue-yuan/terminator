from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.openapi.utils import get_openapi as _get_openapi

from utils.security import jwt_scheme


class AuthAPIRouter(APIRouter):
    def __init__(self, *, prefix="", tags=None, dependencies=None, responses=None) -> None:
        super().__init__(
            prefix=prefix,
            tags=tags,
            dependencies=[
                Depends(jwt_scheme),
            ],
            responses=responses,
        )


def generate_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def get_openapi(app):
    def openapi():
        if not app.openapi_schema:
            app.openapi_schema = _get_openapi(
                title=app.title,
                version=app.version,
                openapi_version=app.openapi_version,
                description=app.description,
                terms_of_service=app.terms_of_service,
                contact=app.contact,
                license_info=app.license_info,
                routes=app.routes,
                tags=app.openapi_tags,
                servers=app.servers,
            )
            for _, method_item in app.openapi_schema.get("paths").items():
                for _, param in method_item.items():
                    responses = param.get("responses")
                    if "422" in responses:
                        del responses["422"]
        return app.openapi_schema
    return openapi
