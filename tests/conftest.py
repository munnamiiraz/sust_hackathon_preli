from datetime import datetime

from app.schemas.ticket import TransactionEntry


def make_tx(
    transaction_id="TXN-1",
    timestamp="2024-01-15T14:30:00Z",
    type="transfer",
    amount=1000.0,
    counterparty="+8801799000001",
    status="completed",
):
    return TransactionEntry(
        transaction_id=transaction_id,
        timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
        type=type,
        amount=amount,
        counterparty=counterparty,
        status=status,
    )
