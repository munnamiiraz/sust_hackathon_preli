from fastapi import APIRouter, Request

from app.controllers.ticket_controller import analyze_ticket
from app.schemas.ticket import TicketRequest, TicketResponse

router = APIRouter(prefix="/v1")


@router.post("/analyze-ticket", response_model=TicketResponse)
async def analyze_ticket_route(request: TicketRequest, http_request: Request):
    return await analyze_ticket(request, http_request)
