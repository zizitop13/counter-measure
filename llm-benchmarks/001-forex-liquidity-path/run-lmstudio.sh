#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${LM_STUDIO_HOST:-http://localhost:1234}"
MODEL="${LM_STUDIO_MODEL:-qwen/qwen3.6-27b}"
REASONING="${LM_STUDIO_REASONING:-on}"
CONTEXT_LENGTH="${LM_STUDIO_CONTEXT_LENGTH:-32768}"
MAX_OUTPUT_TOKENS="${LM_STUDIO_MAX_OUTPUT_TOKENS:-4096}"
TEMPERATURE="${LM_STUDIO_TEMPERATURE:-0}"
TOP_P="${LM_STUDIO_TOP_P:-1}"
TOP_K="${LM_STUDIO_TOP_K:-20}"

usage() {
  cat <<'EOF'
Usage:
  ./run-lmstudio.sh explain nested
  ./run-lmstudio.sh explain guards
  ./run-lmstudio.sh change nested
  ./run-lmstudio.sh change guards

Optional environment variables:
  LM_STUDIO_HOST
  LM_STUDIO_MODEL
  LM_STUDIO_REASONING
  LM_STUDIO_CONTEXT_LENGTH
  LM_STUDIO_MAX_OUTPUT_TOKENS
  LM_STUDIO_TEMPERATURE
  LM_STUDIO_TOP_P
  LM_STUDIO_TOP_K
EOF
}

if [[ $# -ne 2 ]]; then
  usage
  exit 2
fi

TASK="$1"
VARIANT="$2"

case "$TASK" in
  explain) TASK_FILE="$ROOT/prompts/01-explain-path.md" ;;
  change) TASK_FILE="$ROOT/prompts/02-change-request.md" ;;
  *) echo "Unknown task: $TASK" >&2; usage; exit 2 ;;
esac

case "$VARIANT" in
  nested) PLANNER_FILE="$ROOT/src/main/java/dev/countermeasure/llm/liquidity/NestedIfLiquidityPathPlanner.java" ;;
  guards) PLANNER_FILE="$ROOT/src/main/java/dev/countermeasure/llm/liquidity/GuardClauseLiquidityPathPlanner.java" ;;
  *) echo "Unknown variant: $VARIANT" >&2; usage; exit 2 ;;
esac

DOMAIN_FILE="$ROOT/src/main/java/dev/countermeasure/llm/liquidity/LiquidityDomain.java"
INTERFACE_FILE="$ROOT/src/main/java/dev/countermeasure/llm/liquidity/LiquidityPathPlanner.java"
TEST_FILE="$ROOT/src/test/java/dev/countermeasure/llm/liquidity/LiquidityPathPlannerContractTest.java"

for file in "$TASK_FILE" "$DOMAIN_FILE" "$INTERFACE_FILE" "$PLANNER_FILE" "$TEST_FILE"; do
  [[ -f "$file" ]] || { echo "Missing file: $file" >&2; exit 1; }
done

PROMPT_FILE="$(mktemp)"
PAYLOAD_FILE="$(mktemp)"
trap 'rm -f "$PROMPT_FILE" "$PAYLOAD_FILE"' EXIT

{
  cat "$TASK_FILE"
  printf '\n\nFILES PROVIDED:\n'

  printf '\n--- LiquidityDomain.java ---\n'
  cat "$DOMAIN_FILE"

  printf '\n\n--- LiquidityPathPlanner.java ---\n'
  cat "$INTERFACE_FILE"

  printf '\n\n--- %s ---\n' "$(basename "$PLANNER_FILE")"
  cat "$PLANNER_FILE"

  printf '\n\n--- LiquidityPathPlannerContractTest.java ---\n'
  cat "$TEST_FILE"
} > "$PROMPT_FILE"

python3 - "$PROMPT_FILE" "$PAYLOAD_FILE" <<'PY'
import json
import os
import sys

prompt_path, payload_path = sys.argv[1:3]
with open(prompt_path, encoding="utf-8") as f:
    prompt = f.read()

payload = {
    "model": os.environ.get("LM_STUDIO_MODEL", "qwen/qwen3.6-27b"),
    "system_prompt": (
        "You are evaluating an existing Java codebase. Work only from the source "
        "and tests supplied in this request. Do not assume unstated business rules. "
        "The regulatory rules are synthetic benchmark rules, not statements about "
        "real financial regulation. Be precise and concise."
    ),
    "input": prompt,
    "temperature": float(os.environ.get("LM_STUDIO_TEMPERATURE", "0")),
    "top_p": float(os.environ.get("LM_STUDIO_TOP_P", "1")),
    "top_k": int(os.environ.get("LM_STUDIO_TOP_K", "20")),
    "reasoning": os.environ.get("LM_STUDIO_REASONING", "on"),
    "context_length": int(os.environ.get("LM_STUDIO_CONTEXT_LENGTH", "32768")),
    "max_output_tokens": int(os.environ.get("LM_STUDIO_MAX_OUTPUT_TOKENS", "4096")),
    "store": False,
}

with open(payload_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)
PY

mkdir -p "$ROOT/results/raw"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$ROOT/results/raw/${STAMP}-${TASK}-${VARIANT}.json"

echo "POST $HOST/api/v1/chat"
echo "model=$MODEL task=$TASK variant=$VARIANT reasoning=$REASONING"
echo "response=$OUT"

curl --fail-with-body --silent --show-error \
  "$HOST/api/v1/chat" \
  -H "Content-Type: application/json" \
  --data-binary "@$PAYLOAD_FILE" \
  | tee "$OUT"

printf '\n\nSaved raw response to %s\n' "$OUT"
