import json
import logging
import os
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": os.getenv("SERVICE_NAME", "api"),
            "message": record.getMessage(),
        }

        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id

        if hasattr(record, "method"):
            log_record["method"] = record.method

        if hasattr(record, "path"):
            log_record["path"] = record.path

        if hasattr(record, "status_code"):
            log_record["status_code"] = record.status_code

        if hasattr(record, "latency_ms"):
            log_record["latency_ms"] = record.latency_ms

        return json.dumps(log_record)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)