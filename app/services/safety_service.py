from __future__ import annotations

import logging

from app.schemas.ticket import TicketResponse
from app.validators.safety_validator import (
    ACTIONS,
    REPLIES,
    REPLIES_BN,
    contains_forbidden,
    is_prompt_injection,
)

logger = logging.getLogger(__name__)


def apply_safety(response: TicketResponse, complaint: str, language: str = "en") -> TicketResponse:
    complaint = complaint[:5_000]

    if is_prompt_injection(complaint):
        response.human_review_required = True
        if "prompt_injection_detected" not in response.reason_codes:
            response.reason_codes.append("prompt_injection_detected")

    reply_map = REPLIES_BN if language == "bn" else REPLIES
    response.customer_reply          = reply_map.get(response.case_type, reply_map["other"])
    response.recommended_next_action = ACTIONS.get(response.case_type, ACTIONS["other"])

    if response.severity == "critical":
        response.recommended_next_action = "CRITICAL - " + response.recommended_next_action

    if contains_forbidden(response.customer_reply):
        logger.error("SAFETY BUG in customer_reply template")
        response.customer_reply = REPLIES["other"]

    if contains_forbidden(response.recommended_next_action):
        logger.error("SAFETY BUG in recommended_next_action template")
        response.recommended_next_action = ACTIONS["other"]

    return response
