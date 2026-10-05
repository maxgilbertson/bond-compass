"""Upcoming events that move bond markets: central-bank decisions and key inflation and jobs data.

The dates live in data/calendar.json, copied from each central bank's and statistics office's own
published schedule (the source of each is kept with it). Update the file when new years are published.
"""
import json
from datetime import date, timedelta
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "data" / "calendar.json"


def load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"events": [], "checked": None}


def upcoming(days=60, today=None):
    today = today or date.today()
    end = today + timedelta(days=days)
    return [e for e in load().get("events", []) if today.isoformat() <= e["date"] <= end.isoformat()]
