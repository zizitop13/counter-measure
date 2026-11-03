# Golden answer — stock quote selection

The selector evaluates each quote in a fixed first-failure order:

1. disabled source -> SOURCE_DISABLED;
2. symbol unsupported -> SYMBOL_UNSUPPORTED;
3. client region not allowed -> REGION_NOT_ALLOWED;
4. entitlement missing -> ENTITLEMENT_MISSING;
5. timestamp after request.now -> FUTURE_TIMESTAMP;
6. timestamp before request.now - maxQuoteAge -> STALE_QUOTE;
7. invalid price -> INVALID_PRICE;
8. non-positive bid or ask size -> INVALID_SIZE;
9. feed type not allowed by the request -> FEED_TYPE_NOT_ALLOWED;
10. REALTIME mode with a non-realtime quote -> REALTIME_REQUIRED;
11. otherwise -> ACCEPTED.

The first failing rule wins, so check order affects the recorded decision when a quote violates several rules.

A price is valid only when bid and ask are both non-null, both strictly positive, and bid <= ask.

DELAYED_ALLOWED accepts both realtime and delayed quotes after the other checks. REALTIME rejects delayed quotes.

Among ACCEPTED quotes, best bid is the highest bid and best ask is the lowest ask. They may come from different sources.

If no quote is accepted, bestBid, bestBidSource, bestAsk, and bestAskSource are all null.

The time boundaries are inclusive: a quote exactly at now and exactly at now - maxQuoteAge is not rejected by the time checks.
