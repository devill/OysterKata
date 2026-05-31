"""Deterministic reference data (part of the system under test, not an external service)."""

from __future__ import annotations

from datetime import date


class BankHolidayService:
    _HOLIDAYS: frozenset[date] = frozenset(
        {
            date(2026, 4, 3),
            date(2026, 4, 6),
        }
    )

    def is_holiday(self, d: date) -> bool:
        return d in self._HOLIDAYS
