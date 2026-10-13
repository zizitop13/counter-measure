# Automated rubric judge

`judge-answer.sh` evaluates one saved comprehension response against:

- `golden-answer.md`
- `rubric.json`

The LLM judge does **not** receive the Java source and is explicitly told not to solve the original task. Its only role is to map the candidate answer onto the atomic rubric items.

The script then validates the judge JSON and computes the final result deterministically.

## Usage

From `llm-benchmarks/001-forex-liquidity-path`:

```bash
chmod +x judge-answer.sh

./judge-answer.sh results/raw/20261013T165915-explain-nested.json
```

Results are written to:

```text
results/judged/<original-name>.judge.raw.json
results/judged/<original-name>.score.json
```

The normalized score contains:

- one 0/1 score per rubric item;
- evidence per item;
- missing critical items;
- explicit critical errors found by the judge;
- total score;
- deterministic `passed`;
- candidate token statistics;
- judge token statistics.

## Judge model

By default the script uses the same model configured for the benchmark:

```bash
LM_STUDIO_MODEL=qwen/qwen3.6-27b
```

A different local judge model is preferable when available:

```bash
export LM_STUDIO_JUDGE_MODEL='<other-model-id>'
./judge-answer.sh results/raw/...
```

The judge defaults to:

```text
temperature=0
reasoning=off
context_length=32768
max_output_tokens=4096
store=false
```

The judge's token usage is **not** part of the code-clarity result. It is recorded only for diagnostics.

## Trust model

LLM-as-judge is not treated as ground truth.

For the first benchmark runs:

1. run the automated judge;
2. manually inspect every score;
3. correct the rubric or judge prompt if scoring is ambiguous;
4. only later move to sample-based manual audits.

The deterministic pass/fail calculation protects against a judge deciding that a critical mistake is "close enough", but the per-item 0/1 classification is still probabilistic and must be validated.
