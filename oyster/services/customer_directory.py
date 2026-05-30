from __future__ import annotations

from oyster.model import Customer, Programme


class CustomerDirectory:
    _CUSTOMERS: tuple[Customer, ...] = (
        Customer(
            id="alice",
            name="Alice Okafor",
            home_zone=2,
            enrolled=(),
            commuter_club_band=None,
            commuter_club_fee=None,
        ),
        Customer(
            id="bob",
            name="Bob Tremblay",
            home_zone=4,
            enrolled=(Programme.RAILCARD,),
            commuter_club_band=None,
            commuter_club_fee=None,
        ),
        Customer(
            id="carol",
            name="Carol Nweze",
            home_zone=5,
            enrolled=(Programme.ZONE_RESIDENT,),
            commuter_club_band=None,
            commuter_club_fee=None,
        ),
        Customer(
            id="dave",
            name="Dave Lindqvist",
            home_zone=3,
            enrolled=(Programme.COMMUTER_CLUB,),
            commuter_club_band=(1, 3),
            commuter_club_fee=150.0,
        ),
    )

    def all(self) -> list[Customer]:
        return list(self._CUSTOMERS)

    def get(self, customer_id: str) -> Customer:
        for customer in self._CUSTOMERS:
            if customer.id == customer_id:
                return customer
        raise KeyError(f"Unknown customer: {customer_id!r}")
