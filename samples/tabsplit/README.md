# TabSplit

Split shared expenses between friends and work out who pays whom. Pure Python 3.10+, no dependencies.

```python
from tabsplit import Ledger, parse_amount, settle_up

trip = Ledger()
for name in ("Ali", "Sara", "Omar"):
    trip.add_member(name)
trip.add_expense("Ali", parse_amount("90"), description="fuel")          # shared by everyone
trip.add_expense("Sara", parse_amount("45.50"), ["Sara", "Omar"], "dinner")
settle_up(trip.balances())   # [Transfer('Omar', 'Ali', 5275), Transfer('Sara', 'Ali', 725)]
```

Run the example: `python main.py`. Requirements: [`docs/FEATURE_SPEC.md`](docs/FEATURE_SPEC.md).
