# Golden answer — explain liquidity path

This is the reference semantics for the comprehension benchmark. Candidate answers do not need to use the same wording, structure, or terminology, but they must preserve these facts.

## 1. Provider eligibility

A provider is eligible only if all of the following are true:

1. the provider is enabled;
2. it supports the requested currency pair;
3. it admits the request's client region;
4. credit is approved;
5. the quote timestamp is not after `request.now()`;
6. the quote timestamp is not before `request.now() - request.maxQuoteAge()`;
7. available liquidity is strictly greater than zero;
8. the provider's venue is allowed by the request's synthetic regulatory profile.

The quote-age bounds are inclusive: a quote exactly at `now` is valid, and a quote exactly at `now - maxQuoteAge` is valid.

## 2. Provider ordering

After filtering:

- BUY requests use providers in ascending price order;
- SELL requests use providers in descending price order.

## 3. Splitting

The planner uses providers greedily in that sorted order.

For each provider it allocates the smaller of:

- that provider's available amount;
- the amount still remaining to be filled.

Each positive allocation becomes a `Leg`. The planner continues until the request is fully filled or there are no eligible providers left.

## 4. Insufficient liquidity

If eligible providers are exhausted before the request is completely filled:

- all successful partial legs are retained;
- `filledAmount = requestedAmount - remainingAmount`;
- the returned status is `INSUFFICIENT_LIQUIDITY`.

If no amount remains, status is `COMPLETE`.

## 5. Synthetic regulatory profiles

These rules are synthetic benchmark rules:

- `FLEXIBLE`: all venue types are allowed;
- `US_SEF_REQUIRED`: only `SEF` is allowed;
- `EU_MTF_REQUIRED`: only `MTF` is allowed.
