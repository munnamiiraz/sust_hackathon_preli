from __future__ import annotations

import json
import logging
import logging.config
import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import APP_VERSION, CORS_ORIGINS, DOCS_URL, REDOC_URL
from app.routes.health import router as health_router
from app.routes.tickets import router as tickets_router

# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "logging.Formatter",
            "fmt": '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":%(message)s}',
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        }
    },
    "root": {"level": "INFO", "handlers": ["console"]},
})

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Ticket Investigator Copilot",
    version=APP_VERSION,
    description="Rule-based financial ticket analysis API with safety-enforced customer replies.",
    docs_url=DOCS_URL,
    redoc_url=REDOC_URL,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Callable):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(duration_ms)
    return response

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health_router)
app.include_router(tickets_router)

# ---------------------------------------------------------------------------
# Exception handlers — never leak stack traces
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "internal server error"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "validation error", "detail": errors},
    )


@app.exception_handler(json.JSONDecodeError)
async def json_decode_exception_handler(request: Request, exc: json.JSONDecodeError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "malformed JSON", "detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, workers=4)
