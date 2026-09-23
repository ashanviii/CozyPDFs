class DomainError(Exception):
    """Base for domain-layer errors the API layer translates into HTTP
    responses (see the exception handlers registered in api/app.py)."""


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class ValidationError(DomainError):
    pass
