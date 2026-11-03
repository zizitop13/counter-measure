# Task 01 — explain the stock quote-selection algorithm

You are reviewing a Java service that consolidates stock-market quotes from multiple data sources.

Read the production code in this benchmark variant, then explain:

1. Every condition that can accept or reject a quote, including the exact decision produced.
2. Why the order of those checks matters.
3. How REALTIME and DELAYED_ALLOWED modes differ.
4. What makes a price invalid.
5. How the final best bid and best ask are selected.
6. What happens when no quote is accepted.

Be precise enough that another engineer could reimplement the behavior.

Do not propose refactorings. Do not modify the code.
