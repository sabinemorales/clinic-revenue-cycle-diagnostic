"""Display helpers shared by the command line summary and the app."""

from __future__ import annotations


def money(cents: int | float) -> str:
    value = int(round(cents))
    sign = "-" if value < 0 else ""
    value = abs(value)
    return f"{sign}${value // 100:,}.{value % 100:02d}"


def percent(numerator: int | float, denominator: int | float, digits: int = 1) -> str:
    if denominator == 0:
        return "—"
    return f"{(float(numerator) / float(denominator)) * 100:.{digits}f}%"


def hours_from_units(units: int | float) -> float:
    return float(units) * 15 / 60
