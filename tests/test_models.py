import pytest
from pydantic import ValidationError
from app.models import TicketRequest, TransactionEntry

TX_BASE = {
    "transaction_id": "TXN-1",
    "timestamp": "2024-01-15T14:30:00Z",
    "type": "transfer",
    "amount": 1000.0,
    "counterparty": "+8801799000001",
    "status": "completed",
}

REQ_BASE = {
    "ticket_id": "TKT-1",
    "complaint": "I sent money to the wrong number",
}


def test_valid_request():
    req = TicketRequest(**REQ_BASE)
    assert req.ticket_id == "TKT-1"


def test_complaint_stripped_on_input():
    req = TicketRequest(**{**REQ_BASE, "complaint": "  hello  "})
    assert req.complaint == "hello"


def test_complaint_max_length_rejected():
    with pytest.raises(ValidationError):
        TicketRequest(**{**REQ_BASE, "complaint": "x" * 5001})


def test_complaint_whitespace_only_rejected():
    with pytest.raises(ValidationError):
        TicketRequest(**{**REQ_BASE, "complaint": "   "})


def test_ticket_id_max_length_rejected():
    with pytest.raises(ValidationError):
        TicketRequest(**{**REQ_BASE, "ticket_id": "T" * 129})


def test_negative_amount_rejected():
    with pytest.raises(ValidationError):
        TransactionEntry(**{**TX_BASE, "amount": -1.0})


def test_excessive_amount_rejected():
    with pytest.raises(ValidationError):
        TransactionEntry(**{**TX_BASE, "amount": 2_000_000_000.0})


def test_zero_amount_allowed():
    tx = TransactionEntry(**{**TX_BASE, "amount": 0.0})
    assert tx.amount == 0.0


def test_extra_fields_on_request_rejected():
    with pytest.raises(ValidationError):
        TicketRequest(**{**REQ_BASE, "injected": "bad"})


def test_extra_fields_on_transaction_rejected():
    with pytest.raises(ValidationError):
        TransactionEntry(**{**TX_BASE, "injected": "bad"})


def test_transaction_list_over_100_rejected():
    txs = [{**TX_BASE, "transaction_id": f"TXN-{i}"} for i in range(101)]
    with pytest.raises(ValidationError):
        TicketRequest(**{**REQ_BASE, "transaction_history": txs})


def test_transaction_list_100_allowed():
    txs = [{**TX_BASE, "transaction_id": f"TXN-{i}"} for i in range(100)]
    req = TicketRequest(**{**REQ_BASE, "transaction_history": txs})
    assert len(req.transaction_history) == 100


def test_invalid_tx_type_rejected():
    with pytest.raises(ValidationError):
        TransactionEntry(**{**TX_BASE, "type": "wire_transfer"})


def test_invalid_tx_status_rejected():
    with pytest.raises(ValidationError):
        TransactionEntry(**{**TX_BASE, "status": "approved"})


def test_invalid_language_rejected():
    with pytest.raises(ValidationError):
        TicketRequest(**{**REQ_BASE, "language": "fr"})
