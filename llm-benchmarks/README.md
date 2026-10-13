# LLM code-clarity benchmarks

This directory contains controlled code variants for experiments on whether an LLM spends measurably different effort understanding or modifying functionally equivalent code.

These experiments are deliberately separate from `counter-measures/`, which measures runtime performance. The first phase does **not** collect token counts automatically. Run the same prompt manually against each isolated variant in LM Studio and record the model/version/settings and the token statistics reported by LM Studio.

## Rules for experiments

- Keep domain behavior and tests identical between variants.
- Change one readability dimension at a time.
- Use the same model, model configuration, system prompt, context policy, and task for paired runs.
- Start a fresh chat/context for every run.
- Randomize which implementation is tested first.
- Repeat each pair several times before drawing conclusions.
- Correctness is a prerequisite: token count is meaningless if the answer or code change is wrong.
- Treat token usage as a model-specific comprehension-cost proxy, not as a universal "clean-code score".

Current benchmarks:

- [001 — Forex liquidity path: nested conditionals vs guard clauses](001-forex-liquidity-path/README.md)
