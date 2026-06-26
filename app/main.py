from __future__ import annotations

import asyncio
import json
import logging
import logging.config
import os
import time
import uuid
from typing import Callable

import orjson
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models import TicketRequest, TicketResponse
from app.analyzer import analyze
from app.safety import apply_safety

# ---------------------------------------------------------------------------
# Structured JSON logging
# ---------------------------------------------------------------------------

LOGGING_CONFIG = {
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
}

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------

# DOCS_ENABLED=true  → expose /docs and /redoc (default on for hackathon judges)
# DOCS_ENABLED=false → disable in real production
_DOCS_ENABLED = os.getenv("DOCS_ENABLED", "true").lower() == "true"
_docs_url  = "/docs"   if _DOCS_ENABLED else None
_redoc_url = "/redoc"  if _DOCS_ENABLED else None

# CORS_ORIGINS=https://yourdomain.com,https://other.com  (comma-separated)
# Defaults to * when not set — lock down in real production
_raw_origins = os.getenv("CORS_ORIGINS", "*")
_CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",")] if _raw_origins != "*" else ["*"]

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Ticket Investigator Copilot",
    version="1.0.0",
    description="Rule-based financial ticket analysis API with safety-enforced customer replies.",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
)

_START_TIME = time.time()


# ---------------------------------------------------------------------------
# Request ID middleware
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
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health(request: Request):
    return {
        "status": "ok",
        "version": "1.0.0",
        "uptime_seconds": round(time.time() - _START_TIME, 1),
        "request_id": getattr(request.state, "request_id", None),
    }


@app.post("/analyze-ticket", response_model=TicketResponse)
async def analyze_ticket(request: TicketRequest, http_request: Request):
    request_id = getattr(http_request.state, "request_id", "unknown")
    start = time.perf_counter()
    try:
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: apply_safety(analyze(request), request.complaint, request.language or "en"),
            ),
            timeout=28.0,
        )
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            orjson.dumps({
                "request_id": request_id,
                "ticket_id": request.ticket_id,
                "case_type": result.case_type,
                "verdict": result.evidence_verdict,
                "severity": result.severity,
                "department": result.department,
                "tx": result.relevant_transaction_id,
                "duration_ms": duration_ms,
            }).decode()
        )
        return result
    except asyncio.TimeoutError:
        logger.warning(orjson.dumps({"request_id": request_id, "ticket_id": request.ticket_id, "error": "timeout"}).decode())
        return JSONResponse(status_code=503, content={"error": "request timeout"})
    except Exception as e:
        logger.error(orjson.dumps({"request_id": request_id, "error": type(e).__name__, "detail": str(e)}).decode())
        return JSONResponse(status_code=500, content={"error": "internal server error"})


# ---------------------------------------------------------------------------
# Global exception handlers — never leak stack traces
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "internal server error"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Return structured field-level errors without leaking internal paths
    errors = [
        {"field": ".".join(str(l) for l in e["loc"]), "message": e["msg"]}
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
