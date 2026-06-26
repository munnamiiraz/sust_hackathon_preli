"""Analyzer module — rule-based ticket analysis.

Pure rule-based logic (no LLM) that classifies support tickets into case
types, evaluates evidence consistency, determines severity, and produces
a structured response.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.models import TicketRequest, TicketResponse, TransactionEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword sets for case-type classification
# ---------------------------------------------------------------------------

_PHISHING_KEYWORDS = [
    "phishing",
    "scam",
    "fraud",
    "hack",
    "unauthorized",
    "fake sms",
    "fake call",
    "otp",
    "pin",
    "someone called",
    "suspicious call",
    "account tak",
]

_WRONG_TRANSFER_KEYWORDS = [
    "wrong number",
    "wrong account",
    "wrong person",
    "sent to wrong",
    "mistakenly sent",
    "bkash-e",
    "ভুল নম্বর",
    "ভুল",
]

_PAYMENT_FAILED_KEYWORDS = [
    "payment failed",
    "not processed",
    "declined",
    "couldn't pay",
    "could not pay",
    "failed to pay",
    "deducted but",
    "balance cut",
    "balance was deducted",
    "balance deducted",
    "showed failed",
    "app showed",
    "কাটা গেছে",
    "পেমেন্ট হয়নি",
    "charge hoise kintu",
]

_DUPLICATE_PAYMENT_KEYWORDS = [
    "charged twice",
    "double charge",
    "duplicate",
    "paid twice",
    "same payment",
    "deducted twice",
    "debited twice",
    "twice",
    "দুইবার",
    "দুবার",
]

_MERCHANT_KEYWORDS = ["merchant", "shop", "store", "seller"]
_MERCHANT_DELAY_KEYWORDS = ["settlement", "not received", "delay", "pending", "পাইনি"]

_AGENT_KEYWORDS = ["agent", "cash in", "cash-in", "deposit", "এজেন্ট", "ক্যাশ ইন"]
_AGENT_ISSUE_KEYWORDS = ["not credited", "not received", "not added", "missing", "balance", "আসেনি", "জমা হয়নি", "ব্যালেন্সে", "দেখছি না"]

_REFUND_KEYWORDS = [
    "refund",
    "money back",
    "reimburs",
    "ফেরত",
    "টাকা ফেরত",
    "ফেরত দিন",
]

# Map of case_type -> (keyword sets, optional context-AND rule)
_CASE_TYPE_RULES = [
    ("phishing_or_social_engineering", _PHISHING_KEYWORDS, None),
    ("wrong_transfer", _WRONG_TRANSFER_KEYWORDS, None),
    ("payment_failed", _PAYMENT_FAILED_KEYWORDS, None),
    ("duplicate_payment", _DUPLICATE_PAYMENT_KEYWORDS, None),
    (
        "merchant_settlement_delay",
        _MERCHANT_KEYWORDS,
        ("AND", _MERCHANT_DELAY_KEYWORDS),
    ),
    (
        "agent_cash_in_issue",
        _AGENT_KEYWORDS,
        ("AND", _AGENT_ISSUE_KEYWORDS),
    ),
    ("refund_request", _REFUND_KEYWORDS, None),
]


def _any_keyword_in(text: str, keywords: list[str]) -> bool:
    """Return True if any keyword is a substring of text."""
    return any(kw in text for kw in keywords)


def classify_case_type(complaint: str, transactions: list[TransactionEntry]) -> str:
    """Classify the complaint into a case type using keyword matching.

    Rules are checked in order; the first match wins. Falls back to
    tie-breaker rules based on transaction types when no keywords match.
    """
    complaint_lower = _normalize_complaint(complaint).lower()

    for case_type, keywords, context in _CASE_TYPE_RULES:
        if context is None:
            if _any_keyword_in(complaint_lower, keywords):
                return case_type
        else:
            # AND-combine primary keywords with context keywords
            _, ctx_keywords = context
            if _any_keyword_in(complaint_lower, keywords) and _any_keyword_in(
                complaint_lower, ctx_keywords
            ):
                return case_type

    # Tie-breakers based on transaction history
    if transactions:
        if all(tx.type == "settlement" for tx in transactions):
            return "merchant_settlement_delay"
        if all(tx.type == "refund" for tx in transactions):
            return "refund_request"
        # Bangla/non-ASCII complaints: fall back to transaction-type signals
        # when keyword matching fails due to encoding/normalization differences
        has_cash_in = any(tx.type == "cash_in" for tx in transactions)
        has_agent_cp = any(tx.counterparty.upper().startswith("AGENT") for tx in transactions)
        if has_cash_in and has_agent_cp:
            return "agent_cash_in_issue"

    return "other"


# ---------------------------------------------------------------------------
# Transaction relevance scoring
# ---------------------------------------------------------------------------

_AMOUNT_RE = re.compile(r"[\d,]+(?:\.\d+)?")
_DIGIT_RE = re.compile(r"\d+")

# Bangla → ASCII digit map for normalization
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _normalize_complaint(text: str) -> str:
    """Normalize complaint text: Bangla digits → ASCII, strip extra whitespace."""
    return text.translate(_BN_DIGITS).strip()


_FAILURE_WORDS = [
    "failed",
    "not",
    "didn't",
    "problem",
    "issue",
    "wrong",
    "error",
    "missing",
    "হয়নি",
    "পাইনি",
]

_TIME_RE = re.compile(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?\b')
_BN_HOUR_WORDS = {
    "সকাল": 8, "দুপুর": 12, "বিকেল": 15, "সন্ধ্যা": 18, "রাত": 21, "ভোর": 4,
}


def _extract_hours(text: str) -> list[int]:
    """Extract possible hours (0-23) from complaint text."""
    hours = []
    text_norm = _normalize_complaint(text)
    # Bangla time-of-day words give rough hour
    for word, base_hour in _BN_HOUR_WORDS.items():
        if word in text_norm:
            hours.append(base_hour)
    # 12/24-hour numeric times
    for m in _TIME_RE.finditer(text_norm):
        h = int(m.group(1))
        meridiem = (m.group(3) or "").lower()
        if meridiem == "pm" and h < 12:
            h += 12
        elif meridiem == "am" and h == 12:
            h = 0
        if 0 <= h <= 23:
            hours.append(h)
    return hours


_TYPE_HINTS = {
    "transfer": ["transfer", "sent", "send", "পাঠ"],
    "payment": ["payment", "paid", "pay", "bill"],
    "cash_in": ["cash in", "deposit", "জমা"],
    "settlement": ["settlement", "merchant"],
    "refund": ["refund", "ফেরত"],
}


def _extract_amounts(complaint: str) -> list[float]:
    """Extract numeric amounts from complaint text (commas stripped)."""
    raw = _AMOUNT_RE.findall(complaint)
    amounts: list[float] = []
    for token in raw:
        try:
            amounts.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return amounts


def _digits_only(text: str) -> str:
    return "".join(_DIGIT_RE.findall(text))


def _amounts_within(amount: float, targets: list[float], pct: float) -> bool:
    if not targets:
        return False
    for t in targets:
        if t == 0:
            if abs(amount) < 1e-9:
                return True
            continue
        if abs(amount - t) / abs(t) <= pct:
            return True
    return False


def _score_transaction(
    tx: TransactionEntry,
    complaint_lower: str,
    complaint_amounts: list[float],
    complaint_digits: str,
    complaint_hours: list[int],
) -> int:
    score = 0

    # +3 amount match (within 1%)
    if _amounts_within(tx.amount, complaint_amounts, 0.01):
        score += 3

    # +2 counterparty substring match
    cp = (tx.counterparty or "").lower()
    if cp and cp in complaint_lower:
        score += 2

    # +2 last 6 digits of counterparty found in complaint digits
    cp_digits = _digits_only(tx.counterparty or "")
    if len(cp_digits) >= 6:
        tail = cp_digits[-6:]
        if tail in complaint_digits:
            score += 2

    # +1 status-based: failed/reversed + failure words present
    if tx.status in ("failed", "reversed") and _any_keyword_in(
        complaint_lower, _FAILURE_WORDS
    ):
        score += 1

    # +1 type-hint match
    hints = _TYPE_HINTS.get(tx.type, [])
    if hints and any(h in complaint_lower for h in hints):
        score += 1

    # +1 time-of-day match (within 1 hour window)
    if complaint_hours and tx.timestamp:
        tx_hour = tx.timestamp.hour
        if any(abs(tx_hour - ch) <= 1 for ch in complaint_hours):
            score += 1

    return score


def find_relevant_transaction(
    complaint: str, transactions: list[TransactionEntry], case_type: str = "other"
) -> Optional[str]:
    """Return the transaction_id most likely referenced by the complaint."""
    if not transactions:
        return None

    complaint_norm = _normalize_complaint(complaint)
    complaint_lower = complaint_norm.lower()
    complaint_amounts = _extract_amounts(complaint_norm)
    complaint_digits = _digits_only(complaint_norm)
    complaint_hours = _extract_hours(complaint)

    scored = [
        (_score_transaction(tx, complaint_lower, complaint_amounts, complaint_digits, complaint_hours), tx)
        for tx in transactions
    ]
    max_score = max((s for s, _ in scored), default=0)

    if max_score < 2:
        return None

    top = [tx for s, tx in scored if s == max_score]

    # Counterparty-disambiguated transactions
    def cp_match(tx: TransactionEntry) -> bool:
        cp = (tx.counterparty or "").lower()
        cp_digits = _digits_only(tx.counterparty or "")
        return (cp and cp in complaint_lower) or (
            len(cp_digits) >= 6 and cp_digits[-6:] in complaint_digits
        )

    # When multiple transactions share the same amount and counterparty can't be
    # identified from the complaint, return null instead of guessing — unless it's
    # a duplicate_payment where the later transaction is the likely duplicate.
    amount_matched = [tx for _, tx in scored if _amounts_within(tx.amount, complaint_amounts, 0.01)]
    cp_disambiguated = [tx for tx in amount_matched if cp_match(tx)]

    if len(top) > 1:
        if case_type == "duplicate_payment":
            return max(top, key=lambda tx: tx.timestamp).transaction_id
        # All tied on same counterparty → most recent is most relevant
        unique_cps = {tx.counterparty for tx in top}
        if len(unique_cps) == 1:
            return max(top, key=lambda tx: tx.timestamp).transaction_id
        return None  # ambiguous tie

    # Unique top scorer, but check for amount-level ambiguity without counterparty signal
    if len(amount_matched) > 1 and not cp_disambiguated and case_type != "duplicate_payment":
        return None  # can't tell which transaction the complaint refers to

    return top[0].transaction_id


# ---------------------------------------------------------------------------
# Evidence verdict
# ---------------------------------------------------------------------------

_EVIDENCE_FAILURE_WORDS = [
    "failed",
    "didn't",
    "did not",
    "not received",
    "not credited",
    "wrong",
    "issue",
    "problem",
    "error",
    "missing",
    "হয়নি",
    "পাইনি",
    "ব্যর্থ",
]

_EVIDENCE_WRONG_WORDS = ["wrong", "mistaken", "ভুল"]


def decide_evidence_verdict(
    complaint: str,
    transactions: list[TransactionEntry],
    relevant_tx_id: Optional[str],
) -> str:
    """Decide whether transaction data supports or contradicts the complaint."""
    if relevant_tx_id is None or not transactions:
        return "insufficient_data"

    tx = next((t for t in transactions if t.transaction_id == relevant_tx_id), None)
    if tx is None:
        return "insufficient_data"

    cl = _normalize_complaint(complaint).lower()
    failure = any(w in cl for w in _EVIDENCE_FAILURE_WORDS)
    wrong = any(w in cl for w in _EVIDENCE_WRONG_WORDS)

    # Wrong transfer: money moved (completed) to wrong person → consistent,
    # BUT if same counterparty appears in multiple transactions (established
    # recipient pattern), the claim is likely inconsistent.
    if wrong and tx.status == "completed":
        same_cp_count = sum(1 for t in transactions if t.counterparty == tx.counterparty)
        if same_cp_count >= 2:
            return "inconsistent"
        return "consistent"
    # Failure/non-receipt claimed, tx in a failed/pending/reversed state → consistent
    if failure and tx.status in ("failed", "reversed", "pending"):
        return "consistent"
    # Failure claimed, tx completed → inconsistent (data contradicts complaint)
    if failure and tx.status == "completed":
        return "inconsistent"
    # Pending transaction confirms a non-receipt/delay complaint
    if tx.status == "pending":
        return "consistent"
    # No strong failure signal: if the transaction completed, it confirms the
    # customer's account activity — consistent with any claim about that tx
    if tx.status == "completed":
        return "consistent"

    return "insufficient_data"


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

def classify_severity(
    case_type: str,
    evidence_verdict: str,
    transactions: list[TransactionEntry],
    relevant_tx_id: Optional[str],
) -> str:
    """Determine ticket severity from case type, verdict, and amount."""
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


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

_DEPARTMENT_MAP = {
    "wrong_transfer": "dispute_resolution",
    "payment_failed": "payments_ops",
    "refund_request": "dispute_resolution",
    "duplicate_payment": "payments_ops",
    "merchant_settlement_delay": "merchant_operations",
    "agent_cash_in_issue": "agent_operations",
    "phishing_or_social_engineering": "fraud_risk",
    "other": "customer_support",
}


def classify_department(case_type: str) -> str:
    """Map a case_type to the owning department."""
    return _DEPARTMENT_MAP.get(case_type, "customer_support")


def should_require_human_review(
    case_type: str, severity: str, evidence_verdict: str
) -> bool:
    """Decide whether a human agent must review this ticket."""
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

_VERDICT_PHRASES = {
    "consistent": "Transaction history supports the claim.",
    "inconsistent": "Transaction history contradicts the complaint — manual verification required.",
    "insufficient_data": "Insufficient transaction data to verify.",
}


def build_agent_summary(
    case_type: str, evidence_verdict: str, relevant_tx_id: Optional[str]
) -> str:
    """Compose the human-readable agent summary."""
    tx_ref = (
        f"Transaction {relevant_tx_id} identified."
        if relevant_tx_id
        else "No matching transaction in history."
    )
    verdict_phrase = _VERDICT_PHRASES.get(
        evidence_verdict, "Insufficient transaction data to verify."
    )
    case_pretty = case_type.replace("_", " ").title()
    return (
        f"Customer reports a {case_pretty} issue. {tx_ref} {verdict_phrase}"
    )


def build_reason_codes(
    case_type: str,
    evidence_verdict: str,
    relevant_tx_id: Optional[str],
    severity: str,
) -> list[str]:
    """Build the structured list of reason codes for this ticket."""
    codes = [case_type, evidence_verdict]
    if relevant_tx_id:
        codes.append("transaction_match")
    if severity in ("high", "critical"):
        codes.append("escalation_required")
    return codes


def calculate_confidence(
    evidence_verdict: str, relevant_tx_id: Optional[str], case_type: str
) -> float:
    """Compute the analyzer confidence score in [0.1, 1.0]."""
    base = {
        "consistent": 0.85,
        "inconsistent": 0.75,
        "insufficient_data": 0.50,
    }.get(evidence_verdict, 0.50)

    if relevant_tx_id:
        base += 0.05
    if case_type == "other":
        base -= 0.15

    return round(max(0.1, min(1.0, base)), 2)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def analyze(request: TicketRequest) -> TicketResponse:
    """Run the full rule-based analysis pipeline on a ticket request."""
    txns = request.transaction_history or []

    case_type = classify_case_type(request.complaint, txns)
    relevant_tx_id = find_relevant_transaction(request.complaint, txns, case_type)
    evidence = decide_evidence_verdict(request.complaint, txns, relevant_tx_id)
    severity = classify_severity(case_type, evidence, txns, relevant_tx_id)
    department = classify_department(case_type)
    # Refund routing: if the underlying transaction completed and no failure was
    # claimed (change-of-mind, policy refund), route to customer_support.
    # Only contested or failed-payment refunds go to dispute_resolution.
    if case_type == "refund_request":
        failure_claimed = any(w in _normalize_complaint(request.complaint).lower() for w in _EVIDENCE_FAILURE_WORDS)
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
        request.ticket_id,
        case_type,
        severity,
        evidence,
        relevant_tx_id,
    )

    return TicketResponse(
        ticket_id=request.ticket_id,
        relevant_transaction_id=relevant_tx_id,
        evidence_verdict=evidence,
        case_type=case_type,
        severity=severity,
        department=department,
        agent_summary=build_agent_summary(case_type, evidence, relevant_tx_id),
        recommended_next_action="",
        customer_reply="",
        human_review_required=human_review,
        confidence=calculate_confidence(evidence, relevant_tx_id, case_type),
        reason_codes=build_reason_codes(
            case_type, evidence, relevant_tx_id, severity
        ),
    )


# ---------------------------------------------------------------------------
# Legacy stub kept for backward compatibility with existing tests
# ---------------------------------------------------------------------------

def analyze_ticket_text(ticket_id: str, description: Optional[str] = None) -> dict:
    """Legacy stub analyzer. Kept for backward compatibility with existing tests."""
    return {
        "ticket_id": ticket_id,
        "status": "analyzed",
        "severity": "low",
        "recommendation": "No action required (stub)",
    }