# Search evaluation

Ticket: [27 — 50+ 条内容搜索评估](27-search-evaluation.md)
Status: archived — deferred to V1; real library has 3 Items

## Corpus

Record the 50+ real Items before running queries. Include video, podcast, book, and
local sources; do not pick only easy-to-search content.

| Item id | Title | Type | Language | Notes |
| ------- | ----- | ---- | -------- | ----- |
|         |       |      |          |       |

## Pre-registered queries

Write all 30 queries here before looking at results. 10 known-item, 10 exploratory,
10 two-character Chinese terms. Save the same list as the JSON file used by the
script.

| # | Query | Kind | Expected Item ids |
| -: | ----- | ---- | ----------------- |
| 1 |       | known / exploratory / two-char | |
| 2 |       |      | |
| 3 |       |      | |

Query file format:

```json
{
  "queries": [
    {"query": "记忆", "expected": ["<item-id>"]},
    {"query": "一个探索式查询", "expected": []}
  ]
}
```

## Run

```bash
./scripts/evaluate-search.py \
  --base-url https://<host>.<tailnet>.ts.net \
  --queries .scratch/trove-mvp/search-queries.json \
  --out .scratch/trove-mvp/search-evaluation-results.md
```

The script logs in with the password prompt, fetches top-10 per query, prints
evidence snippets and Item types, and computes recall@10 and first relevant rank
for queries with expected Items. Manual judgment remains authoritative; use an LLM
only to suggest candidates.

## Summary

| Metric | Target | Measured |
| ------ | ------ | -------- |
| Queries | 30 pre-registered | |
| Corpus | 50+ Items | |
| recall@10 | record | |
| Mean first relevant rank | record | |
| recall@10 by content type | record in script's "By content type" table | |
| Two-character Chinese queries handled | all | |

## Misses and actions

| Query | Missed Item | Explanation | Action (weights/chunking/index) |
| ----- | ----------- | ----------- | ------------------------------- |
|       |             |             |                                 |
