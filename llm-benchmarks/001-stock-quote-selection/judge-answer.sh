#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="${LM_STUDIO_HOST:-http://localhost:1234}"
MODEL="${LM_STUDIO_JUDGE_MODEL:-${LM_STUDIO_MODEL:-qwen/qwen3.6-27b}}"
REASONING="${LM_STUDIO_JUDGE_REASONING:-off}"
CONTEXT_LENGTH="${LM_STUDIO_JUDGE_CONTEXT_LENGTH:-32768}"
MAX_OUTPUT_TOKENS="${LM_STUDIO_JUDGE_MAX_OUTPUT_TOKENS:-4096}"
TEMPERATURE="${LM_STUDIO_JUDGE_TEMPERATURE:-0}"
TOP_P="${LM_STUDIO_JUDGE_TOP_P:-1}"
TOP_K="${LM_STUDIO_JUDGE_TOP_K:-20}"

if [[ $# -ne 1 ]]; then
  echo "Usage: ./judge-answer.sh results/raw/<benchmark-response>.json" >&2
  exit 2
fi

INPUT_JSON="$1"
[[ -f "$INPUT_JSON" ]] || { echo "Missing benchmark response: $INPUT_JSON" >&2; exit 1; }

GOLDEN="$ROOT/evaluation/golden-answer.md"
RUBRIC="$ROOT/evaluation/rubric.json"
[[ -f "$GOLDEN" ]] || { echo "Missing $GOLDEN" >&2; exit 1; }
[[ -f "$RUBRIC" ]] || { echo "Missing $RUBRIC" >&2; exit 1; }

mkdir -p "$ROOT/results/judged"

BASE="$(basename "$INPUT_JSON" .json)"
PROMPT_FILE="$(mktemp)"
PAYLOAD_FILE="$(mktemp)"
RAW_JUDGE="$ROOT/results/judged/${BASE}.judge.raw.json"
SCORE_FILE="$ROOT/results/judged/${BASE}.score.json"
trap 'rm -f "$PROMPT_FILE" "$PAYLOAD_FILE"' EXIT

python3 - "$INPUT_JSON" "$GOLDEN" "$RUBRIC" "$PROMPT_FILE" <<'PY'
import json
import sys

input_json, golden_path, rubric_path, prompt_path = sys.argv[1:5]

with open(input_json, encoding="utf-8") as f:
    response = json.load(f)

candidate = None
for item in response.get("output", []):
    if item.get("type") == "message":
        candidate = item.get("content")
        break

if not candidate:
    raise SystemExit("Could not find output[type=message].content in benchmark response")

with open(golden_path, encoding="utf-8") as f:
    golden = f.read()

with open(rubric_path, encoding="utf-8") as f:
    rubric = json.load(f)

judge_schema = {
    "items": {
        item["id"]: {
            "score": 0,
            "evidence": "short quote or concise explanation"
        }
        for item in rubric["items"]
    },
    "critical_errors": [],
    "notes": ""
}

prompt = f"""You are a strict evaluator.

Evaluate the CANDIDATE ANSWER only against the GOLDEN ANSWER and RUBRIC below.
Do not solve the original Java problem yourself.
Do not reward style, verbosity, wording similarity, or extra explanation.
For each rubric item:
- score 1 only if the candidate clearly states the required fact correctly;
- otherwise score 0;
- evidence must quote or briefly point to the relevant candidate text;
- a contradiction scores 0 even if the answer is otherwise similar.

For critical_errors, include only errors that are actually present in the candidate.
Do not calculate the final pass/fail result; the caller will do that deterministically.

Return JSON only, with exactly this shape:
{json.dumps(judge_schema, ensure_ascii=False, indent=2)}

GOLDEN ANSWER
=============
{golden}

RUBRIC
======
{json.dumps(rubric, ensure_ascii=False, indent=2)}

CANDIDATE ANSWER
================
{candidate}
"""

with open(prompt_path, "w", encoding="utf-8") as f:
    f.write(prompt)
PY

python3 - "$PROMPT_FILE" "$PAYLOAD_FILE" <<'PY'
import json
import os
import sys

prompt_path, payload_path = sys.argv[1:3]
with open(prompt_path, encoding="utf-8") as f:
    prompt = f.read()

payload = {
    "model": os.environ.get(
        "LM_STUDIO_JUDGE_MODEL",
        os.environ.get("LM_STUDIO_MODEL", "qwen/qwen3.6-27b"),
    ),
    "system_prompt": (
        "You are a deterministic grading component. "
        "Return only valid JSON. Do not add Markdown fences or prose."
    ),
    "input": prompt,
    "temperature": float(os.environ.get("LM_STUDIO_JUDGE_TEMPERATURE", "0")),
    "top_p": float(os.environ.get("LM_STUDIO_JUDGE_TOP_P", "1")),
    "top_k": int(os.environ.get("LM_STUDIO_JUDGE_TOP_K", "20")),
    "reasoning": os.environ.get("LM_STUDIO_JUDGE_REASONING", "off"),
    "context_length": int(os.environ.get("LM_STUDIO_JUDGE_CONTEXT_LENGTH", "32768")),
    "max_output_tokens": int(os.environ.get("LM_STUDIO_JUDGE_MAX_OUTPUT_TOKENS", "4096")),
    "store": False,
}

with open(payload_path, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)
PY

echo "POST $HOST/api/v1/chat"
echo "judge_model=$MODEL reasoning=$REASONING"
echo "candidate=$INPUT_JSON"

curl --fail-with-body --silent --show-error \
  "$HOST/api/v1/chat" \
  -H "Content-Type: application/json" \
  --data-binary "@$PAYLOAD_FILE" \
  > "$RAW_JUDGE"

python3 - "$INPUT_JSON" "$RAW_JUDGE" "$RUBRIC" "$SCORE_FILE" <<'PY'
import json
import sys

candidate_path, judge_path, rubric_path, score_path = sys.argv[1:5]

with open(candidate_path, encoding="utf-8") as f:
    candidate_response = json.load(f)
with open(judge_path, encoding="utf-8") as f:
    judge_response = json.load(f)
with open(rubric_path, encoding="utf-8") as f:
    rubric = json.load(f)

judge_text = None
for item in judge_response.get("output", []):
    if item.get("type") == "message":
        judge_text = item.get("content")
        break

if not judge_text:
    raise SystemExit("Could not find output[type=message].content in judge response")

try:
    judged = json.loads(judge_text)
except json.JSONDecodeError as e:
    raise SystemExit(f"Judge did not return valid JSON: {e}")

expected_ids = [item["id"] for item in rubric["items"]]
actual_items = judged.get("items", {})

missing = [item_id for item_id in expected_ids if item_id not in actual_items]
extra = [item_id for item_id in actual_items if item_id not in expected_ids]
if missing or extra:
    raise SystemExit(f"Judge item mismatch. missing={missing}, extra={extra}")

scores = {}
evidence = {}
for item in rubric["items"]:
    item_id = item["id"]
    entry = actual_items[item_id]
    score = entry.get("score")
    if score not in (0, 1):
        raise SystemExit(f"Invalid score for {item_id}: {score!r}")
    scores[item_id] = score
    evidence[item_id] = entry.get("evidence", "")

critical_missing = [
    item["id"]
    for item in rubric["items"]
    if item.get("critical") and scores[item["id"]] != 1
]
critical_errors = judged.get("critical_errors", [])
if not isinstance(critical_errors, list):
    raise SystemExit("critical_errors must be a JSON array")

total_score = sum(scores.values())
max_score = sum(item["points"] for item in rubric["items"])
minimum = rubric["pass_rule"]["minimum_total_score"]

passed = (
    not critical_missing
    and not critical_errors
    and total_score >= minimum
)

candidate_stats = candidate_response.get("stats", {})
judge_stats = judge_response.get("stats", {})

normalized = {
    "candidate_file": candidate_path,
    "judge_model_instance_id": judge_response.get("model_instance_id"),
    "scores": scores,
    "evidence": evidence,
    "critical_missing": critical_missing,
    "critical_errors": critical_errors,
    "total_score": total_score,
    "max_score": max_score,
    "minimum_total_score": minimum,
    "passed": passed,
    "candidate_stats": {
        "input_tokens": candidate_stats.get("input_tokens"),
        "reasoning_output_tokens": candidate_stats.get("reasoning_output_tokens"),
        "total_output_tokens": candidate_stats.get("total_output_tokens"),
        "time_to_first_token_seconds": candidate_stats.get("time_to_first_token_seconds"),
        "tokens_per_second": candidate_stats.get("tokens_per_second"),
    },
    "judge_stats": {
        "input_tokens": judge_stats.get("input_tokens"),
        "reasoning_output_tokens": judge_stats.get("reasoning_output_tokens"),
        "total_output_tokens": judge_stats.get("total_output_tokens"),
    },
    "judge_notes": judged.get("notes", ""),
}

with open(score_path, "w", encoding="utf-8") as f:
    json.dump(normalized, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(json.dumps(normalized, ensure_ascii=False, indent=2))
PY

echo
echo "Raw judge response: $RAW_JUDGE"
echo "Normalized score:    $SCORE_FILE"
