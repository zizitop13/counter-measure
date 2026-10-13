# 001 — Forex liquidity path: nested conditionals vs guard clauses

## Question

Does an LLM need measurably more effort to understand or modify functionally equivalent Java code when the decision logic is expressed as deeply nested conditionals instead of guard clauses?

This first benchmark intentionally does **not** automate token collection. It provides controlled code, shared tests, and fixed prompts so the paired runs can be executed manually in LM Studio on the same machine.

## Domain

The service builds a liquidity path for a Forex request from multiple providers.

A provider is considered only when it:

1. is enabled;
2. supports the requested currency pair;
3. admits the client's region;
4. has credit approval;
5. has a quote timestamp that is not in the future;
6. has a quote no older than the request's maximum quote age;
7. has positive available liquidity;
8. satisfies the request's synthetic regulatory profile.

Eligible providers are ordered by best price: ascending for BUY and descending for SELL. The requested amount is greedily filled across providers in that order. If eligible liquidity runs out, the planner returns a partial path with `INSUFFICIENT_LIQUIDITY`.

The names SEF, MTF, ECN, and OTC are used to make the generated benchmark domain recognizable. **The regulatory profiles in this benchmark are deliberately simplified and synthetic; they are not descriptions of actual legal requirements.**

## Controlled variants

Both implementations implement the same interface, consume the same immutable domain records, and are verified by the same JUnit contract tests.

- `NestedIfLiquidityPathPlanner`: eligibility and routing decisions use deliberately deep nesting.
- `GuardClauseLiquidityPathPlanner`: the same decisions use early `continue`, `break`, compact selection, and a switch expression.

The benchmark does not claim that these are the only two styles of Java code. They are the first controlled pair.

## Run

Requirements:

- JDK 21+
- Maven 3.9+

From this directory:

```bash
mvn test
```

The tests execute both planners against the same cases and include a direct equivalence assertion.

## Initial LM Studio protocol

For an initial manual experiment:

1. Choose one local model and record the exact model file/quantization and LM Studio version.
2. Fix temperature, context size, system prompt, and any reasoning setting.
3. Give the model only:
   - `LiquidityDomain.java`
   - `LiquidityPathPlanner.java`
   - **one** planner implementation
   - `LiquidityPathPlannerContractTest.java`
   - one prompt from `prompts/`.
4. Start with a fresh context for every run.
5. Alternate which code style is tested first.
6. Record the model's reported input/output/total tokens and whether the result is correct.
7. Repeat each style at least five times before comparing medians.

For Task 01, correctness should be judged against behavior asserted by the tests, not semantic similarity alone.

For Task 02, correctness is objective: apply the model's change to a fresh copy, add/keep the requested tests, then run `mvn test`.

## Why tests are shared

The experiment is about representation, not business behavior. Separate tests would create a confounder: the model might infer different requirements from the test suite. The same test class therefore exercises both implementations.

## Follow-up dimensions

This scenario can grow without changing domains:

- nested conditionals vs guards;
- meaningful names vs abbreviated/ambiguous names;
- small cohesive methods vs excessive extraction/indirection;
- explicit domain types vs maps/generic containers;
- duplicated policy logic vs abstractions;
- hidden mutation vs immutable transformations;
- comments that explain intent vs comments that restate code;
- change tasks that introduce a new regulatory constraint, provider health state, credit tier, venue preference, or route cap.

Do not combine these dimensions in the same experiment until each has been measured independently.
