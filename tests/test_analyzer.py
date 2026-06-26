import pytest

from tests.conftest import make_tx
from app.services.analysis_service import (
    classify_case_type,
    find_relevant_transaction,
    decide_evidence_verdict,
    classify_severity,
    classify_department,
    should_require_human_review,
    calculate_confidence,
)
from app.utils.text import _normalize_complaint, _extract_hours


# ---------------------------------------------------------------------------
# classify_case_type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("complaint,expected", [
    ("I sent money to the wrong number", "wrong_transfer"),
    ("Someone called and asked for my OTP and PIN", "phishing_or_social_engineering"),
    ("My payment failed but balance was deducted", "payment_failed"),
    ("I was charged twice for the same transaction", "duplicate_payment"),
    ("My merchant settlement is delayed and not received", "merchant_settlement_delay"),
    ("I did a cash in at agent but balance not credited", "agent_cash_in_issue"),
    ("I want a refund for my purchase", "refund_request"),
    ("Hello, just checking in", "other"),
    ("আমি ভুল নম্বরে টাকা পাঠিয়েছি", "wrong_transfer"),
    ("আমার পেমেন্ট হয়নি কিন্তু টাকা কাটা গেছে", "payment_failed"),
])
def test_classify_case_type(complaint, expected):
    assert classify_case_type(complaint, []) == expected


def test_phishing_takes_priority_over_wrong_transfer():
    assert classify_case_type("Someone shared wrong OTP to hack my account", []) == "phishing_or_social_engineering"


def test_classify_fallback_settlement_from_tx():
    txs = [make_tx(type="settlement"), make_tx(transaction_id="TXN-2", type="settlement")]
    assert classify_case_type("I have not received my payment", txs) == "merchant_settlement_delay"


# ---------------------------------------------------------------------------
# find_relevant_transaction
# ---------------------------------------------------------------------------

def test_find_by_amount_match():
    tx = make_tx(amount=5000.0)
    assert find_relevant_transaction("I sent 5000 taka to wrong number", [tx]) == "TXN-1"


def test_find_no_tx_returns_none():
    assert find_relevant_transaction("I have a problem", []) is None


def test_find_low_score_returns_none():
    tx = make_tx(amount=9999.0)
    assert find_relevant_transaction("Hello I need help", [tx]) is None


def test_find_counterparty_match_boosts_score():
    tx = make_tx(counterparty="+8801799000001", amount=5000.0)
    result = find_relevant_transaction("I sent 5000 to +8801799000001 by mistake", [tx])
    assert result == "TXN-1"


def test_find_duplicate_picks_latest():
    tx1 = make_tx("TXN-1", "2024-01-15T10:00:00Z", amount=1000.0, counterparty="merchant-a")
    tx2 = make_tx("TXN-2", "2024-01-15T12:00:00Z", amount=1000.0, counterparty="merchant-a")
    result = find_relevant_transaction("I was charged twice 1000", [tx1, tx2], "duplicate_payment")
    assert result == "TXN-2"


def test_find_ambiguous_tie_returns_none():
    tx1 = make_tx("TXN-1", amount=1000.0, counterparty="+8801111111111")
    tx2 = make_tx("TXN-2", amount=1000.0, counterparty="+8802222222222")
    result = find_relevant_transaction("I sent 1000 taka somewhere", [tx1, tx2])
    assert result is None


# ---------------------------------------------------------------------------
# decide_evidence_verdict
# ---------------------------------------------------------------------------

def test_verdict_no_tx_returns_insufficient():
    assert decide_evidence_verdict("I have a problem", [], None) == "insufficient_data"


def test_verdict_wrong_transfer_completed_consistent():
    tx = make_tx(status="completed")
    assert decide_evidence_verdict("I sent to wrong number", [tx], "TXN-1") == "consistent"


def test_verdict_failed_tx_with_failure_complaint_consistent():
    tx = make_tx(status="failed")
    assert decide_evidence_verdict("My payment failed", [tx], "TXN-1") == "consistent"


def test_verdict_completed_tx_with_failure_complaint_inconsistent():
    tx = make_tx(status="completed")
    assert decide_evidence_verdict("payment failed and not received", [tx], "TXN-1") == "inconsistent"


def test_verdict_pending_tx_consistent():
    tx = make_tx(status="pending")
    assert decide_evidence_verdict("I haven't received my money", [tx], "TXN-1") == "consistent"


# ---------------------------------------------------------------------------
# classify_severity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case_type,verdict,expected", [
    ("phishing_or_social_engineering", "consistent", "critical"),
    ("wrong_transfer", "consistent", "high"),
    ("duplicate_payment", "consistent", "high"),
    ("payment_failed", "consistent", "high"),
    ("other", "inconsistent", "high"),
    ("agent_cash_in_issue", "consistent", "medium"),
    ("merchant_settlement_delay", "consistent", "medium"),
    ("refund_request", "insufficient_data", "low"),
])
def test_classify_severity(case_type, verdict, expected):
    assert classify_severity(case_type, verdict, [], None) == expected


# ---------------------------------------------------------------------------
# classify_department
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case_type,expected", [
    ("wrong_transfer", "dispute_resolution"),
    ("payment_failed", "payments_ops"),
    ("refund_request", "dispute_resolution"),
    ("duplicate_payment", "payments_ops"),
    ("merchant_settlement_delay", "merchant_operations"),
    ("agent_cash_in_issue", "agent_operations"),
    ("phishing_or_social_engineering", "fraud_risk"),
    ("other", "customer_support"),
])
def test_classify_department(case_type, expected):
    assert classify_department(case_type) == expected


# ---------------------------------------------------------------------------
# should_require_human_review
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case_type,severity,verdict,expected", [
    ("phishing_or_social_engineering", "critical", "consistent", True),
    ("wrong_transfer", "high", "consistent", True),
    ("other", "high", "insufficient_data", True),
    ("other", "low", "insufficient_data", False),
    ("other", "medium", "consistent", False),
    ("other", "medium", "inconsistent", True),
])
def test_human_review(case_type, severity, verdict, expected):
    assert should_require_human_review(case_type, severity, verdict) is expected


# ---------------------------------------------------------------------------
# calculate_confidence
# ---------------------------------------------------------------------------

def test_confidence_range():
    for verdict in ("consistent", "inconsistent", "insufficient_data"):
        for case_type in ("wrong_transfer", "other", "phishing_or_social_engineering"):
            c = calculate_confidence(verdict, None, case_type)
            assert 0.1 <= c <= 1.0


def test_confidence_higher_with_tx_match():
    without = calculate_confidence("consistent", None, "wrong_transfer")
    with_tx  = calculate_confidence("consistent", "TXN-1", "wrong_transfer")
    assert with_tx > without


def test_confidence_lower_for_other():
    normal = calculate_confidence("consistent", None, "wrong_transfer")
    other  = calculate_confidence("consistent", None, "other")
    assert other < normal


# ---------------------------------------------------------------------------
# Normalization and time extraction
# ---------------------------------------------------------------------------

def test_bangla_digit_normalization():
    assert _normalize_complaint("৫০০০ টাকা") == "5000 টাকা"


def test_normalize_strips_whitespace():
    assert _normalize_complaint("  hello  ") == "hello"


def test_extract_hours_pm():
    assert 14 in _extract_hours("I sent money at 2 PM")


def test_extract_hours_24h():
    assert 14 in _extract_hours("transaction at 14:30")


def test_extract_hours_bangla_dupur():
    assert 12 in _extract_hours("দুপুরে টাকা পাঠিয়েছি")


def test_extract_hours_bangla_sokal():
    assert 8 in _extract_hours("সকালে পাঠিয়েছিলাম")
