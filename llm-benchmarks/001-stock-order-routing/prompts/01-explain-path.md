# Task 01 — explain the stock-order routing algorithm

You are reviewing a Java service that routes a stock order across trading venues.

Read the production code in this benchmark variant, then explain:

1. Every condition that can make a venue eligible or produce a rejection decision, including the exact decision.
2. The differences between MARKET and LIMIT orders.
3. The price rule for LIMIT BUY and LIMIT SELL orders.
4. The routing-profile rules.
5. The order in which eligible venues are consumed for BUY and SELL.
6. How one order is split across venues.
7. How COMPLETE, PARTIAL, and REJECTED are determined, including what happens to already-built legs when partial fills are not allowed.

Be precise enough that another engineer could reimplement the behavior.

Do not propose refactorings. Do not modify the code.
