from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MAX_COMPLAINT_LEN = 5_000
_MAX_TX_COUNT      = 100
_MAX_ID_LEN        = 128


class TransactionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(..., min_length=1, max_length=_MAX_ID_LEN)
    timestamp: datetime
    type: Literal["transfer", "payment", "cash_in", "cash_out", "settlement", "refund"]
    amount: float = Field(..., ge=0.0, le=1_000_000_000.0)
    counterparty: str = Field(..., min_length=1, max_length=256)
    status: Literal["completed", "failed", "pending", "reversed"]


class TicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str = Field(..., min_length=1, max_length=_MAX_ID_LEN)
    complaint: str = Field(..., min_length=1, max_length=_MAX_COMPLAINT_LEN)
    language: Optional[Literal["en", "bn", "mixed"]] = None
    channel: Optional[Literal[
        "in_app_chat", "call_center", "email", "merchant_portal", "field_agent",
    ]] = None
    user_type: Optional[Literal["customer", "merchant", "agent", "unknown"]] = None
    campaign_context: Optional[str] = Field(None, max_length=512)
    transaction_history: Optional[List[TransactionEntry]] = Field(
        default_factory=list, max_length=_MAX_TX_COUNT
    )

    @field_validator("complaint")
    @classmethod
    def complaint_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("complaint cannot be empty or whitespace")
        return v.strip()


class TicketResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    relevant_transaction_id: Optional[str] = None
    evidence_verdict: Literal["consistent", "inconsistent", "insufficient_data"]
    case_type: Literal[
        "wrong_transfer", "payment_failed", "refund_request", "duplicate_payment",
        "merchant_settlement_delay", "agent_cash_in_issue",
        "phishing_or_social_engineering", "other",
    ]
    severity: Literal["low", "medium", "high", "critical"]
    department: Literal[
        "customer_support", "dispute_resolution", "payments_ops",
        "merchant_operations", "agent_operations", "fraud_risk",
    ]
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    reason_codes: List[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
