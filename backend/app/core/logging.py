import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


_STANDARD_LOG_RECORD_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": os.getenv("SERVICE_NAME", "api"),
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_RECORD_FIELDS:
                continue

            if key.startswith("_"):
                continue

            if key in log_record:
                continue

            log_record[key] = self._serialize_value(value)

        if record.exc_info:
            log_record["exception"] = self.formatException(
                record.exc_info
            )

        if record.stack_info:
            log_record["stack_info"] = self.formatStack(
                record.stack_info
            )

        return json.dumps(
            log_record,
            default=str,
            ensure_ascii=False,
        )

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if value is None:
            return None

        if isinstance(
            value,
            (str, int, float, bool, list, dict),
        ):
            return value

        return str(value)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    logging.captureWarnings(True)