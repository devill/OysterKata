"""Simulated external system — returns non-deterministic results; never use in tests or for validation."""

from __future__ import annotations

import random

from oyster.model import Customer, Programme

_KNOWN_IDS: tuple[str, ...] = ("alice", "bob", "carol", "dave")

_NAME_POOL: tuple[str, ...] = (
    "Alice Okafor",
    "Bob Tremblay",
    "Carol Nweze",
    "Dave Lindqvist",
    "Erin Halvorsen",
    "Frank Adeyemi",
    "Grace Petrov",
    "Hugo Marchetti",
)


class CustomerDirectory:
    """Simulated external system — returns non-deterministic results; never use in tests or for validation."""

    def __init__(self) -> None:
        self._rng = random.Random()
        self._cache: dict[str, Customer] = {}

    def all(self) -> list[Customer]:
        return [self.get(customer_id) for customer_id in _KNOWN_IDS]

    def get(self, customer_id: str) -> Customer:
        if customer_id not in _KNOWN_IDS:
            raise KeyError(f"Unknown customer: {customer_id!r}")
        if customer_id not in self._cache:
            self._cache[customer_id] = self._generate(customer_id)
        return self._cache[customer_id]

    def _generate(self, customer_id: str) -> Customer:
        enrolled = tuple(p for p in Programme if self._rng.random() < 0.5)
        if Programme.COMMUTER_CLUB in enrolled:
            low = self._rng.randint(1, 6)
            high = self._rng.randint(low, 6)
            band: tuple[int, int] | None = (low, high)
            fee: float | None = round(self._rng.uniform(50.0, 250.0), 2)
        else:
            band = None
            fee = None
        return Customer(
            id=customer_id,
            name=self._rng.choice(_NAME_POOL),
            home_zone=self._rng.randint(1, 6),
            enrolled=enrolled,
            commuter_club_band=band,
            commuter_club_fee=fee,
        )
