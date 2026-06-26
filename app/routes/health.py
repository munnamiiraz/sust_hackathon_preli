from fastapi import APIRouter, Request

from app.controllers.health_controller import get_health

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    return get_health(request)
