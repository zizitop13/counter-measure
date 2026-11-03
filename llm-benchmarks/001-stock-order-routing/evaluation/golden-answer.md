# Golden answer — stock-order routing

## Venue evaluation

The first failing rule determines each venue's decision:

1. disabled -> DISABLED;
2. requested symbol unsupported -> SYMBOL_UNSUPPORTED;
3. client region not admitted -> REGION_NOT_ADMITTED;
4. trading permission missing -> TRADING_PERMISSION_DENIED;
5. quote timestamp after request.now -> FUTURE_QUOTE;
6. quote timestamp before request.now - maxQuoteAge -> STALE_QUOTE;
7. available quantity <= 0 -> NO_LIQUIDITY;
8. MARKET order on a venue that does not support market orders -> ORDER_TYPE_UNSUPPORTED;
9. LIMIT order whose price violates the limit -> PRICE_OUTSIDE_LIMIT;
10. routing profile rejects the venue -> ROUTING_POLICY_REJECTED;
11. otherwise -> ELIGIBLE.

The time boundaries are inclusive: a quote exactly at now and exactly at now - maxQuoteAge is valid.

## MARKET vs LIMIT

MARKET orders do not apply a limit-price test, but the venue must support market orders.

LIMIT BUY accepts venue prices <= limitPrice.
LIMIT SELL accepts venue prices >= limitPrice.

## Synthetic routing profiles

ANY_VENUE allows every venue type.

LIT_ONLY allows PRIMARY_EXCHANGE and REGIONAL_EXCHANGE only.

NO_DARK_FOR_LARGE_ORDERS rejects DARK_POOL only when requested quantity is greater than 10,000. Quantity exactly 10,000 still allows DARK_POOL.

## Ordering and allocation

Eligible venues are sorted by price ascending for BUY and descending for SELL.

The router greedily takes min(venue.availableQuantity, remainingQuantity) from each eligible venue in sorted order until the order is filled or venues are exhausted.

## Final status

If remaining quantity reaches zero, status is COMPLETE.

If quantity remains and partialFillAllowed is true:
- routed > 0 -> PARTIAL, keeping built legs;
- routed == 0 -> REJECTED.

If quantity remains and partialFillAllowed is false, status is REJECTED and any already-built legs are discarded; routedQuantity becomes 0.
