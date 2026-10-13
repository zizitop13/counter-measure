# Task 01 — explain the liquidity-path algorithm

You are reviewing a Java service that builds a Forex liquidity path.

Read the production code and tests in this benchmark variant, then answer:

1. Which conditions make a liquidity provider eligible or ineligible?
2. In what order are eligible providers used for BUY and SELL requests?
3. How can one request be split across multiple providers?
4. What happens when the eligible liquidity cannot fill the requested amount?
5. Explain the synthetic regulatory profiles and which venue types they permit.

Be precise enough that another engineer could reimplement the behavior from your explanation.

Do not propose refactorings. Do not modify the code.
