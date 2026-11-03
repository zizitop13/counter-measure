# Task 02 — make a behavior change

Add a new display mode named `PRIMARY_ONLY_WHEN_AVAILABLE`.

Required behavior:

- If at least one PRIMARY feed quote passes all existing checks except display-mode handling, only accepted PRIMARY quotes may contribute to the consolidated best bid/ask.
- If no PRIMARY quote passes those checks, other allowed feed types may contribute normally.
- Existing REALTIME and DELAYED_ALLOWED behavior must remain unchanged.
- Add unit tests for:
  - a valid PRIMARY quote plus a better ALTERNATIVE quote;
  - no valid PRIMARY quote;
  - a PRIMARY quote that is present but rejected by an existing rule.

Make the smallest clear change you consider appropriate and ensure the full test suite passes.
