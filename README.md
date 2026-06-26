# Ticket Investigator Copilot

A rule-based API that classifies customer support tickets, matches complaint text against transaction history, and routes cases to the correct department — with safety-enforced customer replies.

## Setup

### With Docker (recommended)

```bash
docker build -t ticket-api .
docker run -p 8000:8000 ticket-api
```

### Without Docker

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API will be available at `http://localhost:8000`

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/analyze-ticket` | Analyze a support ticket |

## Tech Stack

- **Python 3.11**
- **FastAPI** — REST framework
- **Pydantic v2** — request/response validation
- **Uvicorn** — ASGI server
- **Docker** — containerized deployment

## AI / Model Approach

**No external AI model or LLM is used.** All logic is deterministic rule-based code.

### Evidence Reasoning

Each transaction is scored against the complaint:
- Amount match within 1% tolerance → +3 points
- Counterparty name/number substring in complaint → +2 points
- Last 6 digits of transaction ID in complaint → +2 points
- Transaction status signals claim type (failed/completed) → +1 point
- Transaction type hint (cash_in, transfer, etc.) → +1 point

The highest-scoring transaction is selected as `relevant_transaction_id`. When two transactions tie with no disambiguation signal, `null` is returned (ambiguous case).

### Evidence Verdict Logic

- Complaint implies failure + transaction status is failed/reversed/pending → `consistent`
- Complaint implies failure + transaction status is completed → `inconsistent`
- Wrong transfer + completed + established recipient pattern → `inconsistent`
- Wrong transfer + completed + new recipient → `consistent`
- No transaction history → `insufficient_data`

### Case Classification

Keyword priority chain (first match wins):

`phishing_or_social_engineering` → `wrong_transfer` → `payment_failed` → `duplicate_payment` → `merchant_settlement_delay` → `agent_cash_in_issue` → `refund_request` → `other`

Bangla keyword support included. Falls back to transaction metadata (type + counterparty prefix) when Unicode keyword matching is unreliable.

## Safety Logic

All customer-facing replies use **pre-vetted static templates**. The system:

- **Never asks for credentials** — no PIN, OTP, password, CVV, or card number
- **Never promises refunds** — uses "any eligible amount will be returned through official channels"
- **Never links to third parties** — no WhatsApp, Telegram, Facebook, or external URLs
- **Detects prompt injection** — complaint text is treated as data only; injection patterns (ignore instructions, act as, jailbreak, etc.) are flagged in `reason_codes` and set `human_review_required: true`
- **Bangla language support** — if `language: "bn"` is set, the customer reply is returned in Bangla

## MODELS

| Component | Model/Method |
|-----------|-------------|
| Case classification | Rule-based keyword matching |
| Evidence reasoning | Transaction scoring algorithm |
| Department routing | Deterministic mapping |
| Customer reply | Static pre-vetted templates (EN + BN) |
| Safety filtering | Regex pattern matching |

**No external AI models, APIs, or paid services are used.**

## Sample Request

```http
POST /analyze-ticket
Content-Type: application/json

{
  "ticket_id": "TKT-SAMPLE-01",
  "complaint": "I sent 5000 taka to the wrong number by mistake. Please help me recover it.",
  "language": "en",
  "transaction_history": [
    {
      "transaction_id": "TXN-9101",
      "timestamp": "2026-04-14T14:22:00Z",
      "type": "transfer",
      "amount": 5000.0,
      "counterparty": "+8801711111111",
      "status": "completed"
    }
  ]
}
```

## Sample Response

See [sample_output.json](sample_output.json) for the full response.

```json
{
  "ticket_id": "TKT-SAMPLE-01",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports a Wrong Transfer issue. Transaction TXN-9101 identified. Transaction history supports the claim.",
  "recommended_next_action": "Escalate to dispute_resolution. Verify transaction and initiate recovery process per policy.",
  "customer_reply": "Thank you for reaching out. We have received your report regarding a transfer concern. Our team will investigate thoroughly. Any eligible amount will be processed through official channels. A specialist will personally review your case. For further assistance, please contact our official support channels.",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": ["wrong_transfer", "consistent", "transaction_match", "escalation_required"]
}
```

## Assumptions and Limitations

- Complaint keyword matching may miss highly paraphrased or creative phrasing
- Bangla detection falls back to transaction metadata when Unicode normalization differs between environments
- Stateless — no database, no session persistence
- Ambiguous multi-transaction cases return `null` for `relevant_transaction_id` rather than guessing
- Language detection is caller-provided via the `language` field (not auto-detected)

## Environment

No API keys or secrets required. See `.env.example`:

```
PORT=8000
```
