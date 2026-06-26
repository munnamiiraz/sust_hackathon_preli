from __future__ import annotations

import logging
from typing import Any, Optional, cast

from app.schemas.ticket import TicketRequest, TicketResponse, TransactionEntry
from app.utils.text import (
    _normalize_complaint,
    _extract_amounts,
    _extract_hours,
    _digits_only,
    _amounts_within,
    _any_keyword_in,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Case-type keyword sets
# ---------------------------------------------------------------------------

_PHISHING_KEYWORDS = [
    "phishing", "scam", "fraud", "hack", "unauthorized",
    "fake sms", "fake call", "otp", "pin",
    "someone called", "suspicious call", "account tak",
]
_WRONG_TRANSFER_KEYWORDS = [
    "wrong number", "wrong account", "wrong person",
    "sent to wrong", "mistakenly sent", "bkash-e", "ভুল নম্বর", "ভুল",
]
_PAYMENT_FAILED_KEYWORDS = [
    "payment failed", "not processed", "declined", "couldn't pay", "could not pay",
    "failed to pay", "deducted but", "balance cut", "balance was deducted",
    "balance deducted", "showed failed", "app showed",
    "কাটা গেছে", "পেমেন্ট হয়নি", "charge hoise kintu",
]
_DUPLICATE_PAYMENT_KEYWORDS = [
    "charged twice", "double charge", "duplicate", "paid twice",
    "same payment", "deducted twice", "debited twice", "twice", "দুইবার", "দুবার",
]
_MERCHANT_KEYWORDS = ["merchant", "shop", "store", "seller"]
_MERCHANT_DELAY_KEYWORDS = ["settlement", "not received", "delay", "pending", "পাইনি"]
_AGENT_KEYWORDS = ["agent", "cash in", "cash-in", "deposit", "এজেন্ট", "ক্যাশ ইন"]
_AGENT_ISSUE_KEYWORDS = [
    "not credited", "not received", "not added", "missing", "balance",
    "আসেনি", "জমা হয়নি", "ব্যালেন্সে", "দেখছি না",
]
_REFUND_KEYWORDS = ["refund", "money back", "reimburs", "ফেরত", "টাকা ফেরত", "ফেরত দিন"]

_CASE_TYPE_RULES = [
    ("phishing_or_social_engineering", _PHISHING_KEYWORDS, None),
    ("wrong_transfer", _WRONG_TRANSFER_KEYWORDS, None),
    ("payment_failed", _PAYMENT_FAILED_KEYWORDS, None),
    ("duplicate_payment", _DUPLICATE_PAYMENT_KEYWORDS, None),
    ("merchant_settlement_delay", _MERCHANT_KEYWORDS, ("AND", _MERCHANT_DELAY_KEYWORDS)),
    ("agent_cash_in_issue", _AGENT_KEYWORDS, ("AND", _AGENT_ISSUE_KEYWORDS)),
    ("refund_request", _REFUND_KEYWORDS, None),
]

_FAILURE_WORDS = [
    "failed", "not", "didn't", "problem", "issue", "wrong", "error", "missing",
    "হয়নি", "পাইনি",
]
_EVIDENCE_FAILURE_WORDS = [
    "failed", "didn't", "did not", "not received", "not credited",
    "wrong", "issue", "problem", "error", "missing",
    "হয়নি", "পাইনি", "ব্যর্থ",
]
_EVIDENCE_WRONG_WORDS = ["wrong", "mistaken", "ভুল"]

_TYPE_HINTS: dict[str, list[str]] = {
    "transfer": ["transfer", "sent", "send", "পাঠ"],
    "payment": ["payment", "paid", "pay", "bill"],
    "cash_in": ["cash in", "deposit", "জমা"],
    "settlement": ["settlement", "merchant"],
    "refund": ["refund", "ফেরত"],
}

_DEPARTMENT_MAP: dict[str, str] = {
    "wrong_transfer": "dispute_resolution",
    "payment_failed": "payments_ops",
    "refund_request": "dispute_resolution",
    "duplicate_payment": "payments_ops",
    "merchant_settlement_delay": "merchant_operations",
    "agent_cash_in_issue": "agent_operations",
    "phishing_or_social_engineering": "fraud_risk",
    "other": "customer_support",
}

_VERDICT_PHRASES: dict[str, str] = {
    "consistent": "Transaction history supports the claim.",
    "inconsistent": "Transaction history contradicts the complaint — manual verification required.",
    "insufficient_data": "Insufficient transaction data to verify.",
}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_case_type(complaint: str, transactions: list[TransactionEntry]) -> str:
    complaint_lower = _normalize_complaint(complaint).lower()

    for case_type, keywords, context in _CASE_TYPE_RULES:
        if context is None:
            if _any_keyword_in(complaint_lower, keywords):
                return case_type
        else:
            _, ctx_keywords = context
            if _any_keyword_in(complaint_lower, keywords) and _any_keyword_in(complaint_lower, ctx_keywords):
                return case_type

    if transactions:
        if all(tx.type == "settlement" for tx in transactions):
            return "merchant_settlement_delay"
        if all(tx.type == "refund" for tx in transactions):
            return "refund_request"
        has_cash_in  = any(tx.type == "cash_in" for tx in transactions)
        has_agent_cp = any(tx.counterparty.upper().startswith("AGENT") for tx in transactions)
        if has_cash_in and has_agent_cp:
            return "agent_cash_in_issue"

    return "other"


# ---------------------------------------------------------------------------
# Transaction scoring
# ---------------------------------------------------------------------------

def _score_transaction(
    tx: TransactionEntry,
    complaint_lower: str,
    complaint_amounts: list[float],
    complaint_digits: str,
    complaint_hours: list[int],
) -> int:
    score = 0

    if _amounts_within(tx.amount, complaint_amounts, 0.01):
        score += 3

    cp = (tx.counterparty or "").lower()
    if cp and cp in complaint_lower:
        score += 2

    cp_digits = _digits_only(tx.counterparty or "")
    if len(cp_digits) >= 6 and cp_digits[-6:] in complaint_digits:
        score += 2

    if tx.status in ("failed", "reversed") and _any_keyword_in(complaint_lower, _FAILURE_WORDS):
        score += 1

    hints = _TYPE_HINTS.get(tx.type, [])
    if hints and any(h in complaint_lower for h in hints):
        score += 1

    if complaint_hours and tx.timestamp:
        tx_hour = tx.timestamp.hour
        if any(abs(tx_hour - ch) <= 1 for ch in complaint_hours):
            score += 1

    return score


def find_relevant_transaction(
    complaint: str,
    transactions: list[TransactionEntry],
    case_type: str = "other",
) -> Optional[str]:
    if not transactions:
        return None

    complaint_norm    = _normalize_complaint(complaint)
    complaint_lower   = complaint_norm.lower()
    complaint_amounts = _extract_amounts(complaint_norm)
    complaint_digits  = _digits_only(complaint_norm)
    complaint_hours   = _extract_hours(complaint)

    scored = [
        (_score_transaction(tx, complaint_lower, complaint_amounts, complaint_digits, complaint_hours), tx)
        for tx in transactions
    ]
    max_score = max((s for s, _ in scored), default=0)

    if max_score < 2:
        return None

    top = [tx for s, tx in scored if s == max_score]

    def cp_match(tx: TransactionEntry) -> bool:
        cp = (tx.counterparty or "").lower()
        cp_digits = _digits_only(tx.counterparty or "")
        return (cp and cp in complaint_lower) or (
            len(cp_digits) >= 6 and cp_digits[-6:] in complaint_digits
        )

    amount_matched    = [tx for _, tx in scored if _amounts_within(tx.amount, complaint_amounts, 0.01)]
    cp_disambiguated  = [tx for tx in amount_matched if cp_match(tx)]

    if len(top) > 1:
        if case_type == "duplicate_payment":
            return max(top, key=lambda tx: tx.timestamp).transaction_id
        unique_cps = {tx.counterparty for tx in top}
        if len(unique_cps) == 1:
            return max(top, key=lambda tx: tx.timestamp).transaction_id
        return None

    if len(amount_matched) > 1 and not cp_disambiguated and case_type != "duplicate_payment":
        return None

    return top[0].transaction_id


# ---------------------------------------------------------------------------
# Evidence verdict
# ---------------------------------------------------------------------------

def decide_evidence_verdict(
    complaint: str,
    transactions: list[TransactionEntry],
    relevant_tx_id: Optional[str],
) -> str:
    if relevant_tx_id is None or not transactions:
        return "insufficient_data"

    tx = next((t for t in transactions if t.transaction_id == relevant_tx_id), None)
    if tx is None:
        return "insufficient_data"

    cl      = _normalize_complaint(complaint).lower()
    failure = any(w in cl for w in _EVIDENCE_FAILURE_WORDS)
    wrong   = any(w in cl for w in _EVIDENCE_WRONG_WORDS)

    if wrong and tx.status == "completed":
        same_cp_count = sum(1 for t in transactions if t.counterparty == tx.counterparty)
        return "inconsistent" if same_cp_count >= 2 else "consistent"

    if failure and tx.status in ("failed", "reversed", "pending"):
        return "consistent"
    if failure and tx.status == "completed":
        return "inconsistent"
    if tx.status == "pending":
        return "consistent"
    if tx.status == "completed":
        return "consistent"

    return "insufficient_data"


# ---------------------------------------------------------------------------
# Severity & routing
# ---------------------------------------------------------------------------

def classify_severity(
    case_type: str,
    evidence_verdict: str,
    transactions: list[TransactionEntry],
    relevant_tx_id: Optional[str],
) -> str:
    amount = 0.0
    if relevant_tx_id:
        tx = next((t for t in transactions if t.transaction_id == relevant_tx_id), None)
        if tx is not None:
            amount = tx.amount

    if case_type == "phishing_or_social_engineering":
        return "critical"
    if evidence_verdict == "inconsistent":
        return "high"
    if case_type in ("wrong_transfer", "duplicate_payment") and evidence_verdict == "consistent":
        return "high"
    if case_type == "wrong_transfer" and amount >= 5000:
        return "high"
    if case_type == "duplicate_payment":
        return "high"
    if case_type == "payment_failed" and evidence_verdict == "consistent":
        return "high"
    if case_type == "agent_cash_in_issue" and evidence_verdict == "consistent":
        return "medium"
    if case_type == "merchant_settlement_delay":
        return "medium"
    if case_type == "refund_request":
        return "low" if evidence_verdict == "insufficient_data" else "medium"
    if evidence_verdict == "insufficient_data":
        return "low"
    return "medium"


def classify_department(case_type: str) -> str:
    return _DEPARTMENT_MAP.get(case_type, "customer_support")


def should_require_human_review(case_type: str, severity: str, evidence_verdict: str) -> bool:
    if severity in ("high", "critical"):
        return True
    if evidence_verdict == "inconsistent":
        return True
    if case_type in ("wrong_transfer", "duplicate_payment", "phishing_or_social_engineering"):
        return True
    if case_type == "refund_request" and severity in ("medium", "high", "critical"):
        return True
    return False


# ---------------------------------------------------------------------------
# Summary builders
# ---------------------------------------------------------------------------

def build_agent_summary(case_type: str, evidence_verdict: str, relevant_tx_id: Optional[str]) -> str:
    tx_ref = (
        f"Transaction {relevant_tx_id} identified."
        if relevant_tx_id
        else "No matching transaction in history."
    )
    verdict_phrase = _VERDICT_PHRASES.get(evidence_verdict, "Insufficient transaction data to verify.")
    case_pretty    = case_type.replace("_", " ").title()
    return f"Customer reports a {case_pretty} issue. {tx_ref} {verdict_phrase}"


def build_reason_codes(
    case_type: str,
    evidence_verdict: str,
    relevant_tx_id: Optional[str],
    severity: str,
) -> list[str]:
    codes = [case_type, evidence_verdict]
    if relevant_tx_id:
        codes.append("transaction_match")
    if severity in ("high", "critical"):
        codes.append("escalation_required")
    return codes


def calculate_confidence(evidence_verdict: str, relevant_tx_id: Optional[str], case_type: str) -> float:
    base = {"consistent": 0.85, "inconsistent": 0.75, "insufficient_data": 0.50}.get(evidence_verdict, 0.50)
    if relevant_tx_id:
        base += 0.05
    if case_type == "other":
        base -= 0.15
    return round(max(0.1, min(1.0, base)), 2)


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def analyze(request: TicketRequest) -> TicketResponse:
    txns = request.transaction_history or []

    case_type      = classify_case_type(request.complaint, txns)
    relevant_tx_id = find_relevant_transaction(request.complaint, txns, case_type)
    evidence       = decide_evidence_verdict(request.complaint, txns, relevant_tx_id)
    severity       = classify_severity(case_type, evidence, txns, relevant_tx_id)
    department     = classify_department(case_type)

    if case_type == "refund_request":
        failure_claimed = any(
            w in _normalize_complaint(request.complaint).lower()
            for w in _EVIDENCE_FAILURE_WORDS
        )
        relevant_tx_completed = False
        if relevant_tx_id:
            _tx = next((t for t in txns if t.transaction_id == relevant_tx_id), None)
            if _tx and _tx.status == "completed":
                relevant_tx_completed = True
        if relevant_tx_completed and not failure_claimed:
            department = "customer_support"
        elif severity == "low":
            department = "customer_support"

    human_review = should_require_human_review(case_type, severity, evidence)

    logger.info(
        "ticket=%s case_type=%s severity=%s verdict=%s tx=%s",
        request.ticket_id, case_type, severity, evidence, relevant_tx_id,
    )

    return TicketResponse(
        ticket_id=request.ticket_id,
        relevant_transaction_id=relevant_tx_id,
        evidence_verdict=cast(Any, evidence),
        case_type=cast(Any, case_type),
        severity=cast(Any, severity),
        department=cast(Any, department),
        agent_summary=build_agent_summary(case_type, evidence, relevant_tx_id),
        recommended_next_action="",
        customer_reply="",
        human_review_required=human_review,
        confidence=calculate_confidence(evidence, relevant_tx_id, case_type),
        reason_codes=build_reason_codes(case_type, evidence, relevant_tx_id, severity),
    )
