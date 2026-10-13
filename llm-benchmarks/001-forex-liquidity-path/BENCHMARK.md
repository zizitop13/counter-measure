# Semi-manual LM Studio benchmark scenario

This is the canonical first-pass procedure for benchmark 001. It intentionally uses **curl plus the real source files** instead of copying Java into JSON fixtures.

LM Studio's current native v1 chat endpoint is `POST /api/v1/chat`. The request can fix `temperature`, `top_p`, `top_k`, `reasoning`, `context_length`, and `max_output_tokens`. Keep them unchanged within one benchmark series.

## 0. Prerequisites

- LM Studio running locally.
- Qwen3.6-27B loaded.
- `curl` and `python3` available.
- JDK 21+ and Maven available for validating change tasks.

From the benchmark directory:

```bash
cd llm-benchmarks/001-forex-liquidity-path
```

Make the runner executable once:

```bash
chmod +x run-lmstudio.sh
```

## 1. Confirm the model before the series

Inspect LM Studio's local model list:

```bash
curl --silent http://localhost:1234/api/v1/models
```

Record the exact model/quantization and LM Studio version in `results/manual-runs.csv`.

The runner defaults to:

```text
model=qwen/qwen3.6-27b
temperature=0
top_p=1
top_k=20
reasoning=on
context_length=32768
max_output_tokens=4096
store=false
```

If LM Studio exposes your installed model under a different id:

```bash
export LM_STUDIO_MODEL='<exact-model-id>'
```

Do not change that value within a comparison series.

## 2. Verify the Java baseline

Before asking the model anything:

```bash
mvn test
```

Both implementations must pass the same contract tests.

## 3. Comprehension benchmark

The script constructs the request at runtime from:

- `prompts/01-explain-path.md`
- `LiquidityDomain.java`
- `LiquidityPathPlanner.java`
- exactly one planner implementation

The model does **not** receive unit tests in the prompt. Tests remain an external correctness oracle for code-change tasks rather than a source of requirements for comprehension.

No Java source is duplicated in request fixtures.

Run the first pair:

```bash
./run-lmstudio.sh explain nested
./run-lmstudio.sh explain guards
```

For the next pair reverse the order:

```bash
./run-lmstudio.sh explain guards
./run-lmstudio.sh explain nested
```

Continue until there are at least five paired runs.

Each raw LM Studio response is saved under `results/raw/`.

For every response, score correctness against [`evaluation/rubric.json`](evaluation/rubric.json), using [`evaluation/golden-answer.md`](evaluation/golden-answer.md) as the reference semantics. See [`evaluation/README.md`](evaluation/README.md) for the scoring rules.

For every response, record in `results/manual-runs.csv`:

- input tokens
- reasoning output tokens
- total output tokens
- time to first token
- tokens/second
- whether the explanation is correct
- any relevant notes

Correctness comes first. A short but wrong answer is not a better result. Embedding similarity is not used as the pass/fail criterion.

## 4. Change benchmark

The change prompt is read directly from `prompts/02-change-request.md`.

Run:

```bash
./run-lmstudio.sh change nested
./run-lmstudio.sh change guards
```

Reverse the order for the next pair and repeat.

The requested output is a unified diff. For each run:

1. Start from a clean copy of the corresponding variant.
2. Apply the model's diff.
3. Run:
   ```bash
   mvn test
   ```
4. Mark `correct=true` only when the requested behavior is implemented and the tests pass.
5. Record token statistics from the LM Studio response.

Do not let a failed patch continue into the next run.

## 5. What we compare

Keep these measurements separate:

- **input tokens** — representation/context cost;
- **reasoning output tokens** — first proxy for model effort;
- **answer/output tokens** — communication/patch size;
- **correctness / test pass** — mandatory outcome;
- TTFT and tokens/sec — diagnostics, not readability measures.

The first useful question is not "which version uses fewer total tokens?" It is:

> When correctness is held constant, does one representation consistently require more model reasoning or produce a lower first-attempt success rate?

## 6. Run-order discipline

Use alternating order to reduce warm-cache/order effects:

```text
pair 1: nested -> guards
pair 2: guards -> nested
pair 3: nested -> guards
pair 4: guards -> nested
pair 5: nested -> guards
```

Use a new stateless API request each time. The runner sends `store=false` and never uses `previous_response_id`.

## 7. Do not change during one series

Do not change any of these halfway through:

- model file / quantization
- LM Studio version
- inference backend
- context length
- reasoning mode
- temperature/top-p/top-k
- source files
- prompt wording
- machine power/performance mode

If any of them changes, start a new series.

## 8. Suggested first experiment

Start only with the comprehension task and five pairs. If the answers are all trivially correct and reasoning counts are nearly identical, the benchmark may be too easy; increase task complexity before collecting a large dataset.

Only after the comprehension protocol looks useful should we spend time on a larger change-task series.
