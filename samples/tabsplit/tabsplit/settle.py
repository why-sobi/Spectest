"""Turn balances into a short list of payments that settles everyone up."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Transfer:
    """`sender` pays `receiver` `cents`."""
    sender: str
    receiver: str
    cents: int


def settle_up(balances: dict[str, int]) -> list[Transfer]:
    """Payments that bring every balance to zero (largest debtor pays largest creditor first)."""
    if sum(balances.values()) != 0:
        raise ValueError("balances must add up to zero")
    owed = {name: c for name, c in balances.items() if c > 0}
    owing = {name: -c for name, c in balances.items() if c < 0}
    transfers = []
    while owing:
        debtor = min(owing, key=lambda name: (-owing[name], name))
        creditor = min(owed, key=lambda name: (-owed[name], name))
        cents = min(owing[debtor], owed[creditor])
        transfers.append(Transfer(debtor, creditor, cents))
        for pot, name in ((owing, debtor), (owed, creditor)):
            pot[name] -= cents
            if pot[name] == 0:
                del pot[name]
    return transfers
