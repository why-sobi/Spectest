"""Tiny example: a weekend trip."""
from tabsplit import Ledger, format_cents, parse_amount, settle_up

trip = Ledger()
for name in ("Ali", "Sara", "Omar"):
    trip.add_member(name)
trip.add_expense("Ali", parse_amount("90"), description="fuel")
trip.add_expense("Sara", parse_amount("45.50"), ["Sara", "Omar"], "dinner")

for name, cents in trip.balances().items():
    print(f"{name:5} {format_cents(cents)}")
for t in settle_up(trip.balances()):
    print(f"{t.sender} pays {t.receiver} {format_cents(t.cents)}")
