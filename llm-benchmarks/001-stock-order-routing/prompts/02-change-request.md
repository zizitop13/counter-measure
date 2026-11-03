# Task 02 — make a behavior change

Add a new synthetic routing profile named `PRIMARY_PREFERRED`.

Required behavior:

- Primary-exchange venues remain eligible normally.
- Non-primary venues are allowed only when no eligible primary-exchange venue exists.
- All existing filtering, order-type, price, freshness, and fill behavior must remain unchanged.
- Add unit tests covering:
  - an eligible primary venue plus a cheaper non-primary venue;
  - no eligible primary venue;
  - a primary venue that is present but rejected by another rule.

This is a synthetic benchmark rule, not a statement about real market regulation.

Make the smallest clear change you consider appropriate and ensure the full test suite passes.
