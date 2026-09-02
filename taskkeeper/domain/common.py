from datetime import date, datetime
from dateutil import parser

def serialize_date(value: str | date | datetime) -> str:
    """Convert a date in various formats to ISO format (YYYY-MM-DD)."""
    if not value:
        return None 
    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    return parser.parse(value, dayfirst=True).date().isoformat()

