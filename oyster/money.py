"""GBP amounts, exact to the penny."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import ClassVar

_PENNY = Decimal("0.01")


def _to_pence(value: float | int | str | Decimal) -> Decimal:
    """Round a raw value to the nearest penny.

    Non-Decimal values go through str() so binary-float noise from the fare
    tables never leaks into the arithmetic.
    """
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    return amount.quantize(_PENNY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, order=True)
class Money:
    """A GBP amount, always exact to the penny.

    Addition and subtraction are exact and stay in pence. Scaling is the only
    operation that can lose precision, so `times` rounds once at the end rather
    than after each ratio.
    """

    amount: Decimal

    ZERO: ClassVar[Money]

    @classmethod
    def of(cls, value: float | int | str | Decimal) -> Money:
        return cls(_to_pence(value))

    @classmethod
    def total(cls, amounts: Iterable[Money]) -> Money:
        total = cls.ZERO
        for amount in amounts:
            total = total + amount
        return total

    def times(self, *ratios: Decimal) -> Money:
        """Scale by every ratio, rounding to the nearest penny only at the end."""
        scaled = self.amount
        for ratio in ratios:
            scaled *= ratio
        return Money(_to_pence(scaled))

    def __add__(self, other: Money) -> Money:
        return Money(self.amount + other.amount)

    def __sub__(self, other: Money) -> Money:
        return Money(self.amount - other.amount)

    def __str__(self) -> str:
        return f"£{self.amount:.2f}"


Money.ZERO = Money(Decimal("0.00"))
