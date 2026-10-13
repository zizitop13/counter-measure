# Semi-manual LM Studio runs from IntelliJ

The benchmark can be run without a custom harness. IntelliJ's HTTP Client sends four fixed requests to the local LM Studio server and LM Studio itself reports token/performance statistics.

## Why Qwen3.6-27B is a useful first model

It is large enough for non-trivial Java/code reasoning, supports reasoning mode, and is still practical to run locally on a 64 GB Apple Silicon machine in quantized form. Do not treat results from one model as universal; the first goal is to determine whether the paired variants produce a stable signal at all.

Record the exact concrete model/quantization used for every series. The virtual model id in the requests is `qwen/qwen3.6-27b`; LM Studio may resolve that to different GGUF/MLX quantizations depending on what you installed.

## Setup

1. Open LM Studio and load Qwen3.6-27B.
2. Start the local server on port 1234 (Developer tab, or `lms server start --port 1234`).
3. Open `lm-studio.http` in IntelliJ.
4. Run request **0** and record the concrete loaded model/quantization and LM Studio version.
5. Run only one benchmark request at a time.
6. Copy the response's `stats` values into `results/manual-runs.csv`.
7. For a paired comparison, use a fresh independent request each time; do not use `previous_response_id`.

All four requests currently fix:

- model: `qwen/qwen3.6-27b`
- temperature: `0`
- top_p: `1`
- top_k: `20`
- reasoning: `on`
- context length: `32768`
- maximum output: `4096`
- state storage: disabled

The native LM Studio `/api/v1/chat` response reports:

- `stats.input_tokens`
- `stats.reasoning_output_tokens`
- `stats.total_output_tokens`
- `stats.tokens_per_second`
- `stats.time_to_first_token_seconds`

## What to compare

Do **not** use only total tokens.

For a fixed task and model, record at least:

1. correctness;
2. reasoning output tokens;
3. total output tokens;
4. input tokens;
5. TTFT and generation speed as diagnostic data.

Input tokens are expected to differ somewhat because the source representations have different textual sizes. That is itself a representation cost, but it should not be confused with reasoning effort. For the readability hypothesis, `reasoning_output_tokens` and correctness are more interesting than `input_tokens`.

For the explanation task, manually score correctness against the contract tests.

For the change task, apply the returned unified diff to a fresh checkout of the corresponding variant and run `mvn test`. A response that uses fewer tokens but does not pass the requested tests is a failed run.

## Run order

With temperature 0, repeated generations may still not be perfectly identical depending on backend/runtime details. Use paired runs and alternate order to reduce systematic warm-cache effects:

```text
run 1: nested -> guards
run 2: guards -> nested
run 3: nested -> guards
...
```

Five pairs are enough for the first exploratory pass. If a signal appears, increase the number of repetitions before making a conference claim.

## Later

After the manual protocol is stable, the same JSON requests can be driven by a tiny local script. Do that only after deciding which metrics and correctness checks are actually useful.
