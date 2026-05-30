from __future__ import annotations


class FareTable:
    _FLAT_FARE = 1.75
    _HOPPER_WINDOW_MINUTES = 60

    _RAIL_SINGLE_WITH_ZONE1: dict[int, dict[str, float]] = {
        1: {"peak": 2.80, "off_peak": 2.70},
        2: {"peak": 3.40, "off_peak": 2.80},
        3: {"peak": 3.70, "off_peak": 2.90},
        4: {"peak": 4.40, "off_peak": 2.90},
        5: {"peak": 5.10, "off_peak": 3.20},
        6: {"peak": 5.60, "off_peak": 3.40},
    }

    _RAIL_SINGLE_OUTER: dict[int, dict[str, float]] = {
        1: {"peak": 1.90, "off_peak": 1.70},
        2: {"peak": 1.90, "off_peak": 1.70},
        3: {"peak": 2.80, "off_peak": 1.80},
    }

    _RAIL_CAPS: dict[str, dict[str, float]] = {
        "Z1-2": {"daily": 8.90, "weekly": 40.00, "monthly": 150.00},
        "Z1-3": {"daily": 10.50, "weekly": 47.00, "monthly": 176.00},
        "Z1-4": {"daily": 12.80, "weekly": 57.50, "monthly": 215.00},
        "Z1-5": {"daily": 15.20, "weekly": 68.00, "monthly": 255.00},
        "Z1-6": {"daily": 16.30, "weekly": 73.00, "monthly": 274.00},
        "outer": {"daily": 6.00, "weekly": 27.00, "monthly": 101.00},
    }

    _BUS_CAPS: dict[str, float] = {"daily": 5.25, "weekly": 26.25, "monthly": 105.00}

    _COMMUTER_CLUB_FEES: dict[str, float] = {
        "Z1-2": 130.00,
        "Z1-3": 150.00,
        "Z1-4": 190.00,
        "Z1-5": 230.00,
        "Z1-6": 260.00,
        "outer": 100.00,
    }

    def flat_fare(self) -> float:
        return self._FLAT_FARE

    def hopper_window_minutes(self) -> int:
        return self._HOPPER_WINDOW_MINUTES

    def rail_single(self, includes_zone1: bool, zones_spanned: int, peak: bool) -> float:
        table = self._RAIL_SINGLE_WITH_ZONE1 if includes_zone1 else self._RAIL_SINGLE_OUTER
        level = "peak" if peak else "off_peak"
        bracket = self._capped_zone_bracket(table, zones_spanned)
        return table[bracket][level]

    def rail_cap(self, band: str, level: str) -> float:
        return self._RAIL_CAPS[band][level]

    def bus_cap(self, level: str) -> float:
        return self._BUS_CAPS[level]

    def commuter_club_fee(self, band: str) -> float:
        try:
            return self._COMMUTER_CLUB_FEES[band]
        except KeyError:
            raise KeyError(f"Unknown commuter club band: {band!r}") from None

    @staticmethod
    def _capped_zone_bracket(table: dict[int, dict[str, float]], zones_spanned: int) -> int:
        highest = max(table)
        return min(zones_spanned, highest)
