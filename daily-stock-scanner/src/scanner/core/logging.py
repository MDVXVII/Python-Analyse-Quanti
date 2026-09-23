"""Journalisation structurée (JSON sur une ligne) pour les exécutions automatisées.

Chaque ligne contient un horodatage UTC, le niveau, le module, le message et des champs
additionnels passés via ``extra={"ctx": {...}}``. Format lisible par un humain en local
(``SCANNER_LOG_FORMAT=text``), JSON par défaut en CI.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ctx = getattr(record, "ctx", None)
        if isinstance(ctx, dict):
            payload.update(ctx)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str | None = None, fmt: str | None = None) -> None:
    """Configure la journalisation racine (idempotent)."""
    level = level or os.environ.get("SCANNER_LOG_LEVEL", "INFO")
    fmt = fmt or os.environ.get("SCANNER_LOG_FORMAT", "json")
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    if fmt == "text":
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")
        )
    else:
        handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Bibliothèques bavardes
    for noisy in ("httpx", "httpcore", "yfinance", "urllib3", "peewee"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
