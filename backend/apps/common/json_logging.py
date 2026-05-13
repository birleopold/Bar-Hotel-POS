"""JSON log lines for production observability (ELK, CloudWatch, etc.)."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import UTC, datetime


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line; works without python-json-logger."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exc_info"] = "".join(traceback.format_exception(*record.exc_info)).strip()
        rid = getattr(record, "request_id", None)
        if rid:
            payload["request_id"] = rid
        if hasattr(record, "tenant_id") and record.tenant_id:
            payload["tenant_id"] = str(record.tenant_id)
        if hasattr(record, "outlet_id") and record.outlet_id:
            payload["outlet_id"] = str(record.outlet_id)
        if hasattr(record, "user_id") and record.user_id:
            payload["user_id"] = str(record.user_id)
        if hasattr(record, "site_id") and record.site_id:
            payload["site_id"] = str(record.site_id)
        # Extra fields from LoggerAdapter or extra={}
        for key in ("duration_ms", "path", "method", "status_code"):
            if hasattr(record, key):
                val = getattr(record, key)
                if val is not None:
                    payload[key] = val
        return json.dumps(payload, default=str, ensure_ascii=False)

    def formatException(self, ei) -> str:  # noqa: N802
        return "".join(traceback.format_exception(*ei)).strip()


def configure_warnings_stream() -> None:
    logging.captureWarnings(True)
