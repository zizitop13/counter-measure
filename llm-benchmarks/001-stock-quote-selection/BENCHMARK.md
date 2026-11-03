# Semi-manual LM Studio benchmark scenario

This benchmark uses curl and reads the real Java files at runtime. Java source is never copied into request JSON fixtures.

## 1. Prerequisites

- LM Studio running locally;
- a loaded model, initially Qwen3.6-27B;
- curl and python3;
- JDK 21+ and Maven.

```bash
cd llm-benchmarks/001-stock-quote-selection
chmod +x run-lmstudio.sh judge-answer.sh
```

## 2. Verify the baseline

```bash
mvn test
```

Both implementations must pass the same contract tests before a benchmark series.

## 3. Inspect the model

```bash
curl --silent http://localhost:1234/api/v1/models
```

Record the exact model, quantization, LM Studio version, and inference settings.

## 4. Comprehension benchmark

Run paired requests:

```bash
./run-lmstudio.sh explain nested
./run-lmstudio.sh explain guards
```

Reverse the order for the next pair:

```bash
./run-lmstudio.sh explain guards
./run-lmstudio.sh explain nested
```

The prompt contains only:

- `StockQuoteDomain.java`;
- `StockQuoteSelector.java`;
- exactly one implementation;
- `prompts/01-explain-path.md`.

Unit tests are deliberately excluded from the prompt.

Each raw response is saved under `results/raw/`.

## 5. Correctness

Grade each response:

```bash
./judge-answer.sh results/raw/<response>.json
```

The judge receives only:

- candidate answer;
- `evaluation/golden-answer.md`;
- `evaluation/rubric.json`.

It does not receive Java source.

During the first experiment manually audit every judge result.

## 6. Measurements

Keep these separate:

- input tokens — representation/context cost;
- reasoning output tokens — model reasoning proxy;
- answer/output tokens;
- correctness and rubric score;
- TTFT and tokens/sec as diagnostics.

Never treat a shorter incorrect answer as better.

## 7. Run order

Use at least five paired runs:

```text
pair 1: nested -> guards
pair 2: guards -> nested
pair 3: nested -> guards
pair 4: guards -> nested
pair 5: nested -> guards
```

Do not change model, quantization, context length, reasoning mode, inference parameters, source files, or prompt wording within one series.

## 8. Change task

After the comprehension benchmark is stable:

```bash
./run-lmstudio.sh change nested
./run-lmstudio.sh change guards
```

Validate every proposed change against a clean copy with `mvn test`.
