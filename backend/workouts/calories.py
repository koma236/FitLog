"""Fixed MET gross estimates; round once at the final value."""

from decimal import ROUND_HALF_UP, Decimal

MET = {"general": Decimal("3.5"), "squat": Decimal("5.0"), "vigorous": Decimal("6.0")}


def calculate(
    weight: Decimal | None, age: int | None, minutes: int | None, kind: str | None
) -> int | None:
    if weight is None or age is None or not 19 <= age <= 59 or minutes is None or kind not in MET:
        return None
    return int((MET[kind] * weight * minutes / 60).quantize(Decimal(1), rounding=ROUND_HALF_UP))
