from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Forbidden content patterns
# ---------------------------------------------------------------------------

_FORBIDDEN: list[tuple[str, str]] = [
    (r"\b(pin|otp|one.time.password|password|passcode|card\s*number|cvv|secret\s*code)\b", "credential_request"),
    (r"\b(share|provide|send|enter|confirm|verify)\s+(your\s+)?(pin|otp|password|passcode)\b", "credential_request"),
    (r"\bwe\s+will\s+(refund|return|send\s+back|credit)\b", "refund_promise"),
    (r"\byou\s+will\s+(receive|get)\s+(your\s+)?(money|refund|amount)\b", "refund_promise"),
    (r"\brefund\s+(has\s+been|will\s+be)\s+(processed|initiated|sent)\b", "refund_promise"),
    (r"\byour\s+refund\s+is\b", "refund_promise"),
    (r"\b(whatsapp|telegram|facebook|instagram)\b", "third_party"),
    (r"https?://", "external_link"),
    (r"www\.", "external_link"),
]

_INJECTION: list[str] = [
    r"ignore\s+(all\s+)?(previous|prior|above|your)?\s*(instructions?|rules?|prompts?|constraints?)",
    r"you\s+are\s+now\s+a",
    r"new\s+(instructions?|system\s+prompt)",
    r"\bdisregard\b",
    r"\bact\s+as\b",
    r"\bpretend\s+(you\s+are|to\s+be)\b",
    r"\bjailbreak\b",
    r"forget\s+(all\s+)?(previous|prior)?\s*(instructions?|rules?)",
    r"\bsystem\s*:\s*",
    r"\[system\]",
    r"<\s*system\s*>",
]


def contains_forbidden(text: str) -> list[str]:
    t = text.lower()
    return [vtype for pat, vtype in _FORBIDDEN if re.search(pat, t)]


def is_prompt_injection(text: str) -> bool:
    t = text.lower()
    hit = any(re.search(p, t) for p in _INJECTION)
    if hit:
        logger.warning("Prompt injection detected")
    return hit


# ---------------------------------------------------------------------------
# Pre-vetted static reply templates — never ask for credentials or promise refunds
# ---------------------------------------------------------------------------

REPLIES: dict[str, str] = {
    "wrong_transfer": (
        "Thank you for reaching out. We have received your report regarding a transfer concern. "
        "Our team will investigate thoroughly. Any eligible amount will be processed through official channels. "
        "A specialist will personally review your case. "
        "For further assistance, please contact our official support channels."
    ),
    "payment_failed": (
        "Thank you for contacting us. We understand your concern about the payment issue. "
        "Our payments team will review the transaction details. "
        "Any eligible amount will be returned through official channels. "
        "For further assistance, please contact our official support channels."
    ),
    "refund_request": (
        "Thank you for your message. We have noted your request. "
        "Our team will review your case and any eligible amount will be returned through official channels. "
        "A specialist will personally review your case. "
        "For further assistance, please contact our official support channels."
    ),
    "duplicate_payment": (
        "Thank you for reporting this. We have recorded your concern regarding a possible duplicate charge. "
        "Our team will investigate and any eligible amount will be returned through official channels. "
        "For further assistance, please contact our official support channels."
    ),
    "merchant_settlement_delay": (
        "Thank you for contacting us. We have noted your merchant settlement concern. "
        "Our merchant operations team will review and follow up within the standard processing window. "
        "For further assistance, please contact our official support channels."
    ),
    "agent_cash_in_issue": (
        "Thank you for reaching out. We have received your cash-in report. "
        "Our agent operations team will investigate. "
        "Any eligible amount will be credited through official channels. "
        "For further assistance, please contact our official support channels."
    ),
    "phishing_or_social_engineering": (
        "Thank you for reporting this security concern. We take this very seriously. "
        "Please do not share any personal information with unknown contacts. "
        "Our security team has been alerted. "
        "For further assistance, please contact our official support channels."
    ),
    "other": (
        "Thank you for contacting us. A support specialist will review your case. "
        "For further assistance, please contact our official support channels."
    ),
}

REPLIES_BN: dict[str, str] = {
    "wrong_transfer": "আপনার হস্তান্তর সংক্রান্ত অভিযোগটি আমরা গ্রহণ করেছি। আমাদের দল বিষয়টি তদন্ত করবে। যোগ্য পরিমাণ অফিসিয়াল চ্যানেলের মাধ্যমে প্রক্রিয়া করা হবে। একজন বিশেষজ্ঞ আপনার কেসটি পর্যালোচনা করবেন। অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না। আরও সহায়তার জন্য আমাদের অফিসিয়াল সাপোর্ট চ্যানেলে যোগাযোগ করুন।",
    "payment_failed": "আপনার পেমেন্ট সমস্যার বিষয়টি আমরা গ্রহণ করেছি। আমাদের পেমেন্টস দল লেনদেনের বিবরণ পর্যালোচনা করবে। যোগ্য পরিমাণ অফিসিয়াল চ্যানেলের মাধ্যমে ফেরত দেওয়া হবে। অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না। আরও সহায়তার জন্য আমাদের অফিসিয়াল সাপোর্ট চ্যানেলে যোগাযোগ করুন।",
    "refund_request": "আপনার অনুরোধটি আমরা গ্রহণ করেছি। আমাদের দল আপনার কেসটি পর্যালোচনা করবে এবং যোগ্য পরিমাণ অফিসিয়াল চ্যানেলের মাধ্যমে ফেরত দেওয়া হবে। অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না। আরও সহায়তার জন্য আমাদের অফিসিয়াল সাপোর্ট চ্যানেলে যোগাযোগ করুন।",
    "duplicate_payment": "সম্ভাব্য ডুপ্লিকেট চার্জের বিষয়টি আমরা নথিভুক্ত করেছি। আমাদের দল তদন্ত করবে এবং যোগ্য পরিমাণ অফিসিয়াল চ্যানেলের মাধ্যমে ফেরত দেওয়া হবে। অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না। আরও সহায়তার জন্য আমাদের অফিসিয়াল সাপোর্ট চ্যানেলে যোগাযোগ করুন।",
    "merchant_settlement_delay": "আপনার মার্চেন্ট সেটেলমেন্ট সংক্রান্ত উদ্বেগটি আমরা নথিভুক্ত করেছি। আমাদের মার্চেন্ট অপারেশন্স দল বিষয়টি পর্যালোচনা করবে এবং অফিসিয়াল চ্যানেলে আপডেট জানাবে। আরও সহায়তার জন্য আমাদের অফিসিয়াল সাপোর্ট চ্যানেলে যোগাযোগ করুন।",
    "agent_cash_in_issue": "আপনার ক্যাশ-ইন সমস্যার বিষয়টি আমরা গ্রহণ করেছি। আমাদের এজেন্ট অপারেশন্স দল এটি দ্রুত যাচাই করবে এবং যোগ্য পরিমাণ অফিসিয়াল চ্যানেলে জমা করা হবে। অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না। আরও সহায়তার জন্য আমাদের অফিসিয়াল সাপোর্ট চ্যানেলে যোগাযোগ করুন।",
    "phishing_or_social_engineering": "এই নিরাপত্তা সংক্রান্ত বিষয়টি জানানোর জন্য ধন্যবাদ। আমরা এটি অত্যন্ত গুরুত্বের সাথে নিচ্ছি। অনুগ্রহ করে অপরিচিত কারো সাথে কোনো ব্যক্তিগত তথ্য শেয়ার করবেন না। আমাদের নিরাপত্তা দলকে সতর্ক করা হয়েছে। আরও সহায়তার জন্য আমাদের অফিসিয়াল সাপোর্ট চ্যানেলে যোগাযোগ করুন।",
    "other": "আপনার অভিযোগটি আমরা গ্রহণ করেছি। একজন সাপোর্ট বিশেষজ্ঞ আপনার কেসটি পর্যালোচনা করবেন। আরও সহায়তার জন্য আমাদের অফিসিয়াল সাপোর্ট চ্যানেলে যোগাযোগ করুন।",
}

ACTIONS: dict[str, str] = {
    "wrong_transfer": "Escalate to dispute_resolution. Verify transaction and initiate recovery process per policy.",
    "payment_failed": "Route to payments_ops. Confirm if balance was deducted without completion. Initiate reversal per policy if confirmed.",
    "refund_request": "Route to dispute_resolution. Verify transaction eligibility and process per refund policy.",
    "duplicate_payment": "Escalate to payments_ops. Verify duplicate charge and initiate reversal for extra deduction per policy.",
    "merchant_settlement_delay": "Route to merchant_operations. Verify settlement status and expected timeline.",
    "agent_cash_in_issue": "Route to agent_operations. Verify cash-in with agent records and credit if confirmed.",
    "phishing_or_social_engineering": "URGENT: Route to fraud_risk immediately. Flag account for security review.",
    "other": "Route to customer_support for manual review.",
}
