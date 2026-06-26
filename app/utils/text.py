from __future__ import annotations

import re

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_AMOUNT_RE  = re.compile(r"[\d,]+(?:\.\d+)?")
_DIGIT_RE   = re.compile(r"\d+")
_TIME_RE    = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?\b")

_BN_HOUR_WORDS: dict[str, int] = {
    "সকাল": 8, "দুপুর": 12, "বিকেল": 15,
    "সন্ধ্যা": 18, "রাত": 21, "ভোর": 4,
}


def _normalize_complaint(text: str) -> str:
    return text.translate(_BN_DIGITS).strip()


def _digits_only(text: str) -> str:
    return "".join(_DIGIT_RE.findall(text))


def _extract_amounts(complaint: str) -> list[float]:
    amounts: list[float] = []
    for token in _AMOUNT_RE.findall(complaint):
        try:
            amounts.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return amounts


def _extract_hours(text: str) -> list[int]:
    hours: list[int] = []
    text_norm = _normalize_complaint(text)
    for word, base_hour in _BN_HOUR_WORDS.items():
        if word in text_norm:
            hours.append(base_hour)
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


def _any_keyword_in(text: str, keywords: list[str]) -> bool:
    return any(kw in text for kw in keywords)


def _amounts_within(amount: float, targets: list[float], pct: float) -> bool:
    for t in targets:
        if t == 0:
            if abs(amount) < 1e-9:
                return True
            continue
        if abs(amount - t) / abs(t) <= pct:
            return True
    return False
