from __future__ import annotations

import asyncio
import logging
import time

import orjson
from fastapi import Request
from fastapi.responses import JSONResponse

from app.schemas.ticket import TicketRequest, TicketResponse
from app.services.analysis_service import analyze
from app.services.safety_service import apply_safety

logger = logging.getLogger(__name__)


async def analyze_ticket(request: TicketRequest, http_request: Request) -> TicketResponse | JSONResponse:
    request_id = getattr(http_request.state, "request_id", "unknown")
    start = time.perf_counter()
    try:
        loop   = asyncio.get_running_loop()
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
                "ticket_id":  request.ticket_id,
                "case_type":  result.case_type,
                "verdict":    result.evidence_verdict,
                "severity":   result.severity,
                "department": result.department,
                "tx":         result.relevant_transaction_id,
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
