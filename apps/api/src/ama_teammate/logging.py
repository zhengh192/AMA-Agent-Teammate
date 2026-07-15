from __future__ import annotations

import logging
import re
from typing import Any

SENSITIVE_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|password|secret|token)(\s*[=:]\s*)([^\s,;]+)"
)


def redact(value: str) -> str:
    return SENSITIVE_PATTERN.sub(r"\1\2[REDACTED]", value)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)


def safe_error_code(exc: BaseException) -> str:
    return type(exc).__name__


def safe_details(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
