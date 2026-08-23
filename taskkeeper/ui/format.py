"""French date formatting without relying on locale.setlocale.

The original app calls locale.setlocale(locale.LC_ALL, 'fr_FR.UTF-8') and
silently falls back if the host doesn't have that locale installed —
this sidesteps that dependency entirely for the two places this mockup
needs a French date string.
"""
from __future__ import annotations

from datetime import date

_WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def format_date_fr(d: date) -> str:
    """'samedi 22 août 2026'"""
    return f"{_WEEKDAYS_FR[d.weekday()]} {d.day} {_MONTHS_FR[d.month - 1]} {d.year}"


def format_date_short_fr(d: date) -> str:
    """'sam. 22 août' — compact form for the reschedule popover."""
    return f"{_WEEKDAYS_FR[d.weekday()][:3]}. {d.day} {_MONTHS_FR[d.month - 1][:4]}"
