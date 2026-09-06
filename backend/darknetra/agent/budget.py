from decimal import Decimal
from typing import Protocol


class HasBudget(Protocol):
    budget_usd: Decimal
    spent_usd: Decimal


def remaining(thread: HasBudget) -> Decimal:
    return max(Decimal("0"), thread.budget_usd - thread.spent_usd)


def charge(thread: HasBudget, cost: Decimal | float | str) -> None:
    amount = Decimal(str(cost))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Cost must be finite and nonnegative")
    thread.spent_usd += amount
