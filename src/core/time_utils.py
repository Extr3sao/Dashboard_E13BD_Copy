from __future__ import annotations

import datetime as dt


UTC = dt.timezone.utc


def utc_now() -> dt.datetime:
    return dt.datetime.now(UTC).replace(microsecond=0)


def utc_now_naive() -> dt.datetime:
    return utc_now().replace(tzinfo=None)


def utc_isoformat(value: dt.datetime) -> str:
    normalized = value.replace(microsecond=0)
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=UTC)
    else:
        normalized = normalized.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z")


def utc_now_iso(value: dt.datetime | None = None) -> str:
    return utc_isoformat(value or utc_now())
