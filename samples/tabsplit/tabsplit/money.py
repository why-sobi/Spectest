"""Money helpers. All amounts are whole cents (int) to avoid floating-point rounding errors."""
import re

AMOUNT = re.compile(r"(\d+)(?:\.(\d{1,2}))?")


def parse_amount(text: str) -> int:
    """Parse a user-typed amount such as "12", "12.5" or "12.50" into cents."""
    match = AMOUNT.fullmatch(text.strip())
    if not match:
        raise ValueError(f"not a valid amount: {text!r}")
    whole, frac = match.groups()
    return int(whole) * 100 + int((frac or "0").ljust(2, "0"))


def format_cents(cents: int) -> str:
    """Format cents for display, e.g. 1250 -> "$12.50" and -305 -> "-$3.05"."""
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) // 100}.{abs(cents) % 100:02d}"


def split_evenly(total_cents: int, n: int) -> list[int]:
    """Split a total into n shares that differ by at most one cent and add up exactly to the total."""
    if n < 1:
        raise ValueError("need at least one share")
    if total_cents < 0:
        raise ValueError("total must not be negative")
    base, remainder = divmod(total_cents, n)
    return [base + 1 if i < remainder else base for i in range(n)]
