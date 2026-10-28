# TabSplit Feature Specification

TabSplit splits shared expenses between a group of friends and works out who pays whom.
All money is stored as whole cents (`int`), never as floats. Everything is importable from the `tabsplit` package.

## parse_amount(text)
- Converts a typed amount into cents: `"12"` → `1200`, `"12.5"` → `1250`, `"12.50"` → `1250`, `"0.07"` → `7`.
- Leading and trailing spaces are ignored: `" 3.20 "` → `320`.
- Raises `ValueError` for anything else, including an empty string, a negative amount (`"-5"`),
  more than two decimals (`"1.234"`), a currency symbol (`"$5"`) or words (`"ten"`).

## format_cents(cents)
- Formats cents for display with a dollar sign and exactly two decimals: `1250` → `"$12.50"`, `7` → `"$0.07"`, `0` → `"$0.00"`.
- Negative amounts get a leading minus sign: `-305` → `"-$3.05"`.

## split_evenly(total_cents, n)
- Splits `total_cents` into a list of `n` shares that add up exactly to `total_cents`.
- Shares differ by at most one cent. The extra cents go to the **first** shares in the list:
  `split_evenly(100, 3)` → `[34, 33, 33]`, `split_evenly(101, 3)` → `[34, 34, 33]`.
- Raises `ValueError` when `n` is less than 1 or `total_cents` is negative. `split_evenly(0, 2)` → `[0, 0]`.

## Ledger
A group's members and expenses. `Ledger()` starts empty: `members` is an empty list and `expenses` is an empty list.

### add_member(name)
- Adds a member and returns the name with surrounding spaces removed. Members keep the order they joined in `members`.
- Raises `ValueError` if the name is empty or only spaces.
- Raises `ValueError` if a member with the same name already exists, ignoring upper/lower case (`"sara"` clashes with `"Sara"`).

### add_expense(payer, amount_cents, participants=None, description="")
- Records that `payer` paid `amount_cents` on behalf of `participants`, appends it to `expenses` and returns it as an
  `Expense(payer, amount_cents, participants, description)`, where `participants` is a tuple.
- When `participants` is omitted, the expense is shared by every current member, in the order they joined.
- The payer does not have to be one of the participants (e.g. paying for someone else's ticket).
- Raises `ValueError` when: the payer is not a member; `amount_cents` is zero or negative; `participants` is an empty
  list; a participant is not a member; or the same participant appears twice. A rejected expense is not recorded.

### balances()
- Returns a dict mapping every member (in joining order) to their net balance in cents:
  what they paid minus their shares of the expenses they took part in.
- Positive means the member is owed money; negative means they owe money. Members with no expenses have `0`.
- Each expense is split with `split_evenly` over its participants in the order they were given, so the first
  participants carry the extra cents. The balances always add up to exactly `0`.
- Example: members Ali, Sara, Omar. Ali pays `9000` for everyone; Sara pays `4550` for Sara and Omar.
  Balances: Ali `6000`, Sara `-725`, Omar `-5275`.

### total_spent()
- Returns the sum of all recorded expenses in cents (`0` when there are none).

## settle_up(balances)
- Takes a dict of balances (as returned by `Ledger.balances()`) and returns a list of `Transfer(sender, receiver, cents)`
  payments that bring everyone to zero. `sender` is a member who owes money, `receiver` is a member who is owed money.
- Raises `ValueError` if the balances do not add up to zero.
- Members with a zero balance never appear in a transfer. An all-zero (or empty) dict gives an empty list.
- Algorithm: repeatedly, the member who owes the most pays the member who is owed the most; the payment is the smaller
  of the two amounts. Ties are broken alphabetically by name. Repeat until all balances are zero.
- Example: `{"Ali": 6000, "Sara": -725, "Omar": -5275}` → `[Transfer("Omar", "Ali", 5275), Transfer("Sara", "Ali", 725)]`.
- Paying a transfer moves the sender's balance **up** by `cents` (towards zero) and the receiver's balance
  **down** by `cents`. So after applying every transfer (`balance[sender] += cents`, `balance[receiver] -= cents`)
  all balances are `0`.
- Example with several debtors: `{"A": 150, "B": -70, "C": -80}` → `[Transfer("C", "A", 80), Transfer("B", "A", 70)]`
  (C owes more than B, so C pays first).
- Every transfer is for a positive number of cents, and there are at most (number of non-zero balances − 1) transfers.
