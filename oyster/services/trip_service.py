from __future__ import annotations

from datetime import datetime

from oyster.model import BillingPeriod, Mode, Trip


def _at(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 4, day, hour, minute)


# Alice: Z1-2 full-month commuter. Three TUBE legs every working day in April
# 2026 (weekdays excluding the two bank holidays):
#   08:10 morning peak: Z2 home (Camden Town) -> Z1 office (Oxford Circus)
#   12:45 midday off-peak: Z1 -> Z1 hop (Oxford Circus -> King's Cross)
#   17:40 evening peak: Z1 -> Z2 reverse commute (Oxford Circus -> Camden Town)
# Uncapped per day = 3.40 + 2.70 + 3.40 = £9.50 (> £8.90 daily cap, so daily
# binds each day). A full Mon-Fri week (~£44.50) exceeds the £40.00 weekly cap,
# and the full month exceeds the £150.00 monthly cap, so the rail cap cascade
# binds at MONTHLY (grand_total £150.00). ~20 working days x 3 legs. Weekdays
# only; bank holidays 2026-04-03 and 2026-04-06 are skipped.
_ALICE_COMMUTE_DAYS: tuple[int, ...] = (
    1, 2, 7, 8, 9, 10, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 27, 28, 29, 30,
)


def _alice_commute() -> tuple[Trip, ...]:
    trips: list[Trip] = []
    for day in _ALICE_COMMUTE_DAYS:
        trips.append(Trip(_at(day, 8, 10), Mode.TUBE, "Camden Town", "Oxford Circus"))
        trips.append(Trip(_at(day, 12, 45), Mode.TUBE, "Oxford Circus", "King's Cross"))
        trips.append(Trip(_at(day, 17, 40), Mode.TUBE, "Oxford Circus", "Camden Town"))
    return tuple(trips)


_ALICE_TRIPS: tuple[Trip, ...] = _alice_commute()


# Bob: Z1-4 student, predominantly off-peak rail so >=80% of taps are off-peak.
# A couple of buses mixed in. Off-peak weekday times are outside 06:30-09:30 and
# 16:00-19:00; bank-holiday taps are off-peak all day. No peak taps at all here.
_BOB_TRIPS: tuple[Trip, ...] = (
    Trip(_at(1, 11, 0), Mode.RAIL, "Harrow-on-the-Hill", "Oxford Circus"),
    Trip(_at(1, 14, 30), Mode.RAIL, "Oxford Circus", "Harrow-on-the-Hill"),
    Trip(_at(2, 10, 15), Mode.RAIL, "Hounslow Central", "King's Cross"),
    Trip(_at(2, 15, 0), Mode.RAIL, "King's Cross", "Hounslow Central"),
    Trip(_at(3, 11, 30), Mode.OVERGROUND, "Harrow-on-the-Hill", "Waterloo"),
    Trip(_at(3, 13, 45), Mode.OVERGROUND, "Waterloo", "Harrow-on-the-Hill"),
    Trip(_at(7, 10, 45), Mode.RAIL, "Hounslow Central", "Liverpool Street"),
    Trip(_at(7, 19, 30), Mode.RAIL, "Liverpool Street", "Hounslow Central"),
    Trip(_at(8, 12, 0), Mode.BUS, "Harrow-on-the-Hill", None),
    Trip(_at(9, 11, 15), Mode.RAIL, "Harrow-on-the-Hill", "Victoria"),
    Trip(_at(9, 20, 0), Mode.RAIL, "Victoria", "Harrow-on-the-Hill"),
    Trip(_at(13, 10, 30), Mode.RAIL, "Hounslow Central", "King's Cross"),
    Trip(_at(13, 15, 15), Mode.RAIL, "King's Cross", "Hounslow Central"),
    Trip(_at(14, 12, 30), Mode.BUS, "Hounslow Central", None),
    Trip(_at(16, 11, 0), Mode.RAIL, "Harrow-on-the-Hill", "Oxford Circus"),
    Trip(_at(16, 14, 0), Mode.RAIL, "Oxford Circus", "Harrow-on-the-Hill"),
)


# Carol: outer Z4-6 resident (home zone 5), heavy bus use plus outer rail with no
# Zone 1, starting in her home zone 5.
# - Hopper window on day 7: three bus taps within 60 min of the first (10:00).
# - A bus tap just OUTSIDE 60 min from that window start (11:05) opens a new
#   window.
# - Enough buses on day 9 to plausibly hit the bus daily cap (£5.25 -> 4 taps).
# - Outer rail legs starting at Cockfosters (Z5).
_CAROL_TRIPS: tuple[Trip, ...] = (
    Trip(_at(7, 10, 0), Mode.BUS, "Cockfosters", None),
    Trip(_at(7, 10, 25), Mode.BUS, "Cockfosters", None),
    Trip(_at(7, 10, 55), Mode.BUS, "Cockfosters", None),
    Trip(_at(7, 11, 5), Mode.BUS, "Cockfosters", None),
    Trip(_at(7, 15, 30), Mode.RAIL, "Cockfosters", "Uxbridge"),
    Trip(_at(8, 9, 45), Mode.BUS, "Cockfosters", None),
    Trip(_at(8, 13, 20), Mode.BUS, "Cockfosters", None),
    Trip(_at(9, 9, 0), Mode.BUS, "Cockfosters", None),
    Trip(_at(9, 9, 30), Mode.BUS, "Cockfosters", None),
    Trip(_at(9, 12, 0), Mode.BUS, "Cockfosters", None),
    Trip(_at(9, 12, 40), Mode.BUS, "Cockfosters", None),
    Trip(_at(9, 17, 15), Mode.BUS, "Cockfosters", None),
    Trip(_at(9, 20, 0), Mode.BUS, "Cockfosters", None),
    Trip(_at(10, 11, 0), Mode.RAIL, "Cockfosters", "Hayes & Harlington"),
    Trip(_at(10, 16, 30), Mode.RAIL, "Hayes & Harlington", "Cockfosters"),
    Trip(_at(13, 10, 30), Mode.BUS, "Cockfosters", None),
    Trip(_at(13, 14, 0), Mode.BUS, "Cockfosters", None),
    Trip(_at(14, 11, 15), Mode.RAIL, "Cockfosters", "Hounslow Central"),
    Trip(_at(14, 13, 45), Mode.TRAM, "Cockfosters", None),
)


# Dave: light traveller, mostly off-peak, uses the 2/3 boundary station
# (Stratford). Commuter-club Z1-3 holder. Not enough volume to bind caps.
_DAVE_TRIPS: tuple[Trip, ...] = (
    Trip(_at(2, 10, 0), Mode.RAIL, "Stratford", "Oxford Circus"),
    Trip(_at(2, 14, 30), Mode.RAIL, "Oxford Circus", "Stratford"),
    Trip(_at(8, 11, 0), Mode.TUBE, "Ealing Broadway", "King's Cross"),
    Trip(_at(8, 15, 0), Mode.TUBE, "King's Cross", "Ealing Broadway"),
    Trip(_at(13, 12, 0), Mode.BUS, "Ealing Broadway", None),
    Trip(_at(20, 10, 30), Mode.RAIL, "Stratford", "Waterloo"),
    Trip(_at(20, 16, 45), Mode.RAIL, "Waterloo", "Stratford"),
    Trip(_at(25, 13, 0), Mode.TUBE, "Lewisham", "King's Cross"),
)


_TRIPS_BY_CUSTOMER: dict[str, tuple[Trip, ...]] = {
    "alice": _ALICE_TRIPS,
    "bob": _BOB_TRIPS,
    "carol": _CAROL_TRIPS,
    "dave": _DAVE_TRIPS,
}


class TripService:
    def trips_for(self, customer_id: str, period: BillingPeriod) -> list[Trip]:
        if customer_id not in _TRIPS_BY_CUSTOMER:
            raise KeyError(f"Unknown customer: {customer_id!r}")
        trips = _TRIPS_BY_CUSTOMER[customer_id]
        in_period = [trip for trip in trips if period.contains(trip.touch_in.date())]
        return sorted(in_period, key=lambda trip: trip.touch_in)
