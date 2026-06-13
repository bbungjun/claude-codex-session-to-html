import re
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Tuple


KST = timezone(timedelta(hours=9))


def coerce_kst(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def parse_timestamp(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return coerce_kst(datetime.fromisoformat(normalized)).replace(microsecond=0).isoformat()
    except ValueError:
        return text


def has_time_reference(query: str) -> bool:
    text = query.strip().lower()
    return bool(
        re.search(r"\b(today|yesterday)\b", text)
        or "오늘" in text
        or "어제" in text
        or re.search(r"\d{1,2}\s*시", text)
        or re.search(r"\b\d{1,2}\s*(am|pm)\b", text)
    )


def strip_time_terms(query: str) -> str:
    text = query
    text = re.sub(r"\b(today|yesterday)\b", " ", text, flags=re.IGNORECASE)
    text = text.replace("오늘", " ").replace("어제", " ")
    text = re.sub(r"\d{1,2}\s*시", " ", text)
    text = re.sub(r"\b\d{1,2}(?::\d{2})?\s*(am|pm)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def resolve_time_range(query: str, now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    current = coerce_kst(now or datetime.now(KST))
    text = query.strip().lower()
    if not text or not has_time_reference(text):
        return datetime(1970, 1, 1, tzinfo=KST), current

    base_date = current.date()
    if "어제" in text or "yesterday" in text:
        base_date = (current - timedelta(days=1)).date()
    elif "오늘" in text or "today" in text:
        base_date = current.date()

    hour = _extract_hour(text)
    if hour is None:
        return (
            datetime.combine(base_date, time(0, 0, 0), tzinfo=KST),
            datetime.combine(base_date, time(23, 59, 59), tzinfo=KST),
        )

    return (
        datetime.combine(base_date, time(hour, 0, 0), tzinfo=KST),
        datetime.combine(base_date, time(hour, 59, 59), tzinfo=KST),
    )


def _extract_hour(text: str) -> Optional[int]:
    korean_match = re.search(r"(\d{1,2})\s*시", text)
    if korean_match:
        hour = int(korean_match.group(1))
        return hour if 0 <= hour <= 23 else None

    english_match = re.search(r"\b(\d{1,2})(?::\d{2})?\s*(am|pm)?\b", text)
    if not english_match:
        return None

    hour = int(english_match.group(1))
    suffix = english_match.group(2)
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    return hour if 0 <= hour <= 23 else None

