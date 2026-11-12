from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Final

from app.core.redaction import mask_text, redact

REDACTION_FAILED_MESSAGE: Final = "log.redaction_failed"


def _json_default(value: object) -> str:
    return mask_text(str(value))


class JsonFormatter(logging.Formatter):
    _reserved = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        # A logging call must never crash the caller or leak unredacted data, so any
        # failure falls back to a fixed record without the original content.
        try:
            return self._format_redacted(record)
        except Exception:
            return json.dumps(
                {
                    "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": REDACTION_FAILED_MESSAGE,
                }
            )

    def _format_redacted(self, record: logging.LogRecord) -> str:
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self._reserved and key not in {"message", "asctime"}
        }
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": mask_text(record.getMessage()),
        }
        payload.update(redact(extras))
        if record.exc_info:
            payload["exception"] = mask_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=_json_default, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
