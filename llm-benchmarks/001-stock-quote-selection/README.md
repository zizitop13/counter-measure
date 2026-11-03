# 001 — Stock quote selection: nested conditionals vs guard clauses

## Question

Does an LLM need measurably more effort to understand or modify functionally equivalent Java code when a decision tree is expressed as deeply nested `if/else` branches instead of guard clauses and early returns?

## Domain

The benchmark consolidates stock-market quotes from multiple data sources. Every source is evaluated against the same ordered rules: source state, symbol, region, entitlement, timestamp, price validity, size, feed type, and realtime requirements.

The first failing rule becomes an observable `QuoteDecision`, so negative branches are real behavior rather than empty `else` blocks.

Accepted quotes are then combined into a consolidated view:

- highest bid wins;
- lowest ask wins;
- bid and ask may come from different sources.

The domain is synthetic and exists only for the benchmark.

## Variants

- `NestedIfStockQuoteSelector` — deliberately deep nested `if/else` logic.
- `GuardClauseStockQuoteSelector` — the same behavior expressed with early returns.

Both implementations share one JUnit contract.

## Run

```bash
mvn test
```

For the LLM experiment follow [BENCHMARK.md](BENCHMARK.md).
