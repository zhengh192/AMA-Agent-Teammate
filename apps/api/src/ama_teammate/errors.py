from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from ama_teammate.domain.models import StructuredError, new_id


class AppError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        category: str,
        message: str,
        recovery: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = StructuredError(
            code=code,
            category=category,
            message=message,
            recovery=recovery,
        )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    correlation_id = request.headers.get("x-correlation-id") or new_id()
    payload = exc.error.model_copy(update={"correlation_id": correlation_id})
    return JSONResponse(status_code=exc.status_code, content={"error": payload.model_dump()})


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation_id = request.headers.get("x-correlation-id") or new_id()
    payload = StructuredError(
        code="internal_error",
        category="internal",
        message="An unexpected error occurred.",
        recovery="Retry the request. If it persists, use the correlation ID in the trace.",
        correlation_id=correlation_id,
    )
    return JSONResponse(status_code=500, content={"error": payload.model_dump()})
