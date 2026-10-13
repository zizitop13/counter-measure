# Correctness evaluation for comprehension answers

## Why not embeddings as the pass/fail mechanism?

Embedding similarity is useful for topical or semantic-nearness search, but it is a poor primary correctness test here.

A candidate can be extremely close to the golden answer in embedding space while containing one small but important contradiction, for example:

- "BUY uses highest price first";
- "quotes exactly at the stale boundary are rejected";
- "US_SEF_REQUIRED allows MTF";
- "partial fills return COMPLETE".

Those answers would share almost all vocabulary and semantics with the reference and could still have very high cosine similarity.

Therefore embeddings may be recorded later as an exploratory metric, but they must not determine correctness.

## Reference artifacts

- `golden-answer.md`: human-readable reference semantics.
- `rubric.json`: atomic facts, critical items, pass threshold, and critical errors.

## Initial scoring process

For the first experimental series, score candidate answers manually against `rubric.json`.

For each rubric item assign:

- 1: clearly present and correct;
- 0: missing, contradicted, or materially ambiguous.

Then apply the pass rule:

1. every critical item must score 1;
2. no critical error may appear;
3. total score must be at least the configured threshold.

The optional inclusive-boundary item lets us distinguish a fully precise answer from one that is functionally correct but omits boundary detail.

## Later: LLM-as-judge

Once the rubric is stable, automate scoring with a separate judge request.

The judge receives:

1. the candidate answer;
2. `golden-answer.md`;
3. `rubric.json`.

It must return only structured JSON containing one score and short evidence for every rubric item plus any critical errors.

Do not use the same generation call that produced the answer as its judge.

Prefer either:

- a different model family as judge; or
- at minimum a separate stateless call with the candidate hidden from any previous context.

For stronger experimental evidence, periodically manually audit a sample of judge decisions.

## Why a rubric is preferable to one holistic score

The benchmark needs to tell the difference between:

- a verbose answer that gets one critical rule wrong;
- a concise answer that covers every required fact;
- an answer that is correct but omits a minor boundary detail.

A single similarity number cannot reliably make those distinctions.

## Optional embedding metric

If embeddings are added later, record cosine similarity to the golden answer only as a secondary diagnostic.

Do not use a fixed threshold such as `cosine > 0.90 => correct` unless it is empirically calibrated against a labeled set containing both subtle correct and subtle incorrect answers.
