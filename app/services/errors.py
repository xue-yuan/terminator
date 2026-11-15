from uuid import UUID


class NotFound(Exception):
    """Resource doesn't exist or isn't visible to the caller."""


class Invalid(Exception):
    """Request is well-formed but refers to something it can't use."""


class Conflict(Exception):
    """Clashes with an existing resource (e.g. a name that is taken)."""

    def __init__(self, message: str, existing_id: UUID | None = None):
        super().__init__(message)
        self.existing_id = existing_id
