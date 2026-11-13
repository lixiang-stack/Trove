# Source success and Tag/summary quality

Ticket: [28 — 来源成功率与 Tag/摘要质量评估](28-source-tag-quality-evaluation.md)
Status: archived — partial evidence; full matrix deferred to V1

Use real content. Do not store copyrighted media in the repository; keep URLs,
error codes, and log tails only.

## Source matrix

| Source | Target | Success | Failure reasons | Notes |
| ------ | ------ | ------- | --------------- | ----- |
| Bilibili | 8/10 |         |                 |       |
| YouTube | 8/10 |         |                 |       |
| Podcast RSS | 8/10 |         |                 |       |
| EPUB | 10/10 |         |                 |       |
| Local file | 10/10 |         |                 |       |

Detailed rows:

| # | Source | URL/path | Result | Reason (network/login/region/DRM/parse/unsupported) | Elapsed | Log tail |
| -: | ------ | -------- | ------ | --------------------------------------------------- | ------- | -------- |
| 1 | Bilibili | | | | | |
| 2 | YouTube | | | | | |
| 3 | Podcast | | | | | |
| 4 | EPUB | | | | | |
| 5 | Local | | | | | |

Failure categories must match the UI messages; there should be no silent failures.
Record the user-actionable hint shown for each failure.

## Summary and Tag quality

Review 20 real Items:

| Item | Summary accurate? | Factual errors | 3–5 Tags | Tags usable? | Notes |
| ---- | ----------------- | -------------- | -------- | ------------ | ----- |
|      |                   |                |          |              |       |

Tag normalization checks:

- [ ] Case-only duplicates are merged.
- [ ] Singular/plural duplicates are merged.
- [ ] Known synonyms reuse the existing Tag.
- [ ] Empty/overlong Tags are rejected.

| Metric | Target | Measured |
| ------ | ------ | -------- |
| Summaries usable | record | |
| Tag usability | ≥70% | |
| Normalization duplicates | none | |

If a target fails, record the action (cookies, UI hint, parser fix, prompt/model
change) and open an improvement issue. Never bypass DRM or regional restrictions.
