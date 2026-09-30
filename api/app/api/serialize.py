"""Turn database values into JSON values for the browser."""

import math
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

type JsonValue = str | int | float | bool | list[JsonValue] | None


def to_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float | Decimal):
        number = float(value)  # Decimal (Postgres numeric) → float, fine for display and charts
        return number if math.isfinite(number) else None  # JSON has no NaN or Infinity
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list | tuple):
        return [to_json_value(item) for item in value]
    return str(value)  # anything else (e.g. tsvector): show its text form
