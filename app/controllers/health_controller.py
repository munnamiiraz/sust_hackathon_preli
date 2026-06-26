from __future__ import annotations

import time

from fastapi import Request

from app.config import APP_VERSION

_START_TIME = time.time()


def get_health(request: Request) -> dict:
    return {
        "status": "ok",
        "version": APP_VERSION,
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "request_id": getattr(request.state, "request_id", None),
    }
