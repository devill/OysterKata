from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oyster.model import BillingPeriod
from oyster.services.customer_directory import CustomerDirectory
from oyster.services.trip_service import TripService


def main() -> None:
    period = BillingPeriod(year=2026, month=4)
    directory = CustomerDirectory()
    trips = TripService()

    print(f"Billing period: {period.label}\n")

    for customer in directory.all():
        customer_trips = trips.trips_for(customer.id, period)
        programmes = ", ".join(p.value for p in customer.enrolled) or "(none)"
        by_mode = Counter(trip.mode.value for trip in customer_trips)
        mode_summary = ", ".join(f"{mode}={count}" for mode, count in sorted(by_mode.items()))

        print(f"{customer.name} ({customer.id})")
        print(f"  enrolled:   {programmes}")
        print(f"  home zone:  {customer.home_zone}")
        print(f"  trips:      {len(customer_trips)}")
        print(f"  by mode:    {mode_summary}")
        print()


if __name__ == "__main__":
    main()
