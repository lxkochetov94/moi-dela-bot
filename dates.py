"""Russian short date/time parser; dates are stored as UTC epoch seconds."""
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ_NAME = os.getenv("BOT_TIMEZONE", "Europe/Moscow")


def tz():
    return ZoneInfo(TZ_NAME)


def fmt(ts):
    if not ts:
        return "Не указан"
    return datetime.fromtimestamp(ts, tz()).strftime("%d.%m.%Y %H:%M")


def parse(value, now=None):
    """Supports 05.11 11:00, 5.11.2026 в 11, сегодня в 18, завтра в 15:30."""
    now = now or datetime.now(tz())
    now = now.astimezone(tz())
    s = str(value).lower().strip().replace(",", " ")
    s = re.sub(r"\s+", " ", s)
    prefix = re.match(r"^(сегодня|завтра)\s*(?:в\s*)?(\d{1,2})(?::(\d{2}))?$", s)
    if prefix:
        delta = 1 if prefix.group(1)=="завтра" else 0
        h, m = int(prefix.group(2)), int(prefix.group(3) or 0)
        if h > 23 or m > 59:
            raise ValueError("Неверное время")
        d = (now + timedelta(days=delta)).date()
        dt = datetime(d.year, d.month, d.day, h, m, tzinfo=tz())
    else:
        match = re.match(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s*(?:в\s*)?(\d{1,2})(?::(\d{2}))?$", s)
        if not match:
            raise ValueError("Введите дату и время, например: 5.11 11:00")
        day, month, year, hh, mm = match.groups()
        year = int(year or now.year)
        h, m = int(hh), int(mm or 0)
        dt = datetime(year, int(month), int(day), h, m, tzinfo=tz())
        if not match.group(3) and dt <= now:
            try:
                dt = dt.replace(year=year + 1)
            except ValueError:
                raise ValueError("Укажите год полностью")
    if dt <= now:
        raise ValueError("Это время уже прошло")
    return int(dt.timestamp())
