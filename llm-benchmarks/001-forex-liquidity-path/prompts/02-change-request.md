# Task 02 — make a behavior change

Add a new synthetic regulatory profile named `UK_NO_OTC_ABOVE_5M`.

Required behavior:

- For requests from `ClientRegion.UK` whose requested amount is greater than 5,000,000, providers with `VenueType.OTC` must be excluded.
- For UK requests of exactly 5,000,000 or less, OTC remains eligible.
- For non-UK requests, this profile imposes no venue restriction.
- All existing behavior must remain unchanged.
- Add unit tests for the boundary (5,000,000), above-boundary case, and a non-UK request.

This is a synthetic benchmark rule, not a statement about real financial regulation.

Make the smallest clear change you consider appropriate and ensure the full test suite passes.
