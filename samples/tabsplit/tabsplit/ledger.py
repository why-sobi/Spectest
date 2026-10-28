"""The group's members and expenses, and who owes what."""
from dataclasses import dataclass

from tabsplit.money import split_evenly


@dataclass(frozen=True)
class Expense:
    """One payment made by a member on behalf of some participants."""
    payer: str
    amount_cents: int
    participants: tuple[str, ...]
    description: str = ""


class Ledger:
    """Members (in the order they joined) and the expenses recorded between them."""

    def __init__(self):
        self.members: list[str] = []
        self.expenses: list[Expense] = []

    def add_member(self, name: str) -> str:
        """Add a member and return the cleaned-up name."""
        name = name.strip()
        if not name:
            raise ValueError("member name is empty")
        if any(m.lower() == name.lower() for m in self.members):
            raise ValueError(f"{name} is already a member")
        self.members.append(name)
        return name

    def add_expense(self, payer: str, amount_cents: int, participants: list[str] | None = None,
                    description: str = "") -> Expense:
        """Record that `payer` paid `amount_cents` for `participants` (default: every member)."""
        if payer not in self.members:
            raise ValueError(f"unknown payer: {payer}")
        if amount_cents <= 0:
            raise ValueError("amount must be positive")
        people = tuple(self.members if participants is None else participants)
        if not people:
            raise ValueError("an expense needs at least one participant")
        if len(set(people)) != len(people):
            raise ValueError("a participant is listed twice")
        unknown = [p for p in people if p not in self.members]
        if unknown:
            raise ValueError(f"unknown participant(s): {', '.join(unknown)}")
        expense = Expense(payer, amount_cents, people, description)
        self.expenses.append(expense)
        return expense

    def balances(self) -> dict[str, int]:
        """Net balance per member in cents: positive = is owed money, negative = owes money."""
        result = {m: 0 for m in self.members}
        for e in self.expenses:
            result[e.payer] += e.amount_cents
            for person, share in zip(e.participants, split_evenly(e.amount_cents, len(e.participants))):
                result[person] -= share
        return result

    def total_spent(self) -> int:
        """Sum of all expenses in cents."""
        return sum(e.amount_cents for e in self.expenses)
