from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

RECALL_LIMIT = 10


@dataclass(frozen=True, slots=True)
class QueryExpectation:
    query: str
    expected: list[str]

    @classmethod
    def from_json(cls, data: Any) -> QueryExpectation:
        if not isinstance(data, dict):
            raise ValueError("query entry must be an object")
        query = str(data.get("query") or "").strip()
        if not query:
            raise ValueError("query must be a non-empty string")
        expected = data.get("expected") or []
        if not isinstance(expected, list) or any(not isinstance(value, str) for value in expected):
            raise ValueError("expected must be a list of item ids")
        return cls(query=query, expected=expected)


def load_expectations(payload: Any) -> list[QueryExpectation]:
    rows: Any
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("queries")
    else:
        raise ValueError("queries file must be a list or an object with a queries list")
    if not isinstance(rows, list) or not rows:
        raise ValueError("queries file must contain at least one query")
    return [QueryExpectation.from_json(row) for row in rows]


def score_query(
    expectation: QueryExpectation,
    results: list[dict[str, Any]],
    *,
    limit: int = RECALL_LIMIT,
) -> dict[str, Any]:
    ranked = results[:limit]
    ranked_ids = [str(row["item"]["id"]) for row in ranked]
    expected_types = {
        str(row["item"]["id"]): str(row["item"].get("source_type"))
        for row in ranked
        if row["item"]["id"] in expectation.expected
    }
    ranks = {
        item_id: (ranked_ids.index(item_id) + 1 if item_id in ranked_ids else None)
        for item_id in expectation.expected
    }
    found = [rank for rank in ranks.values() if rank is not None]
    recall = len(found) / len(ranks) if ranks else None
    first_rank = min(found) if found else None
    return {
        "query": expectation.query,
        "expected": expectation.expected,
        "result_count": len(results),
        "ranks": ranks,
        "recall_at_10": recall,
        "first_relevant_rank": first_rank,
        "missing": [item_id for item_id, rank in ranks.items() if rank is None],
        "expected_types": expected_types,
        "result_types": dict(
            Counter(str(row["item"].get("source_type")) for row in ranked)
        ),
    }


def summarize_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row["expected"]]
    recalls = [row["recall_at_10"] for row in scored if row["recall_at_10"] is not None]
    first_ranks = [
        row["first_relevant_rank"]
        for row in scored
        if row["first_relevant_rank"] is not None
    ]
    types: Counter[str] = Counter()
    by_type: dict[str, dict[str, Any]] = {}
    for row in rows:
        types.update(row["result_types"])
        if not row["expected"]:
            continue
        for item_id, rank in row["ranks"].items():
            kind = row["expected_types"].get(item_id, "unknown")
            bucket = by_type.setdefault(
                kind, {"expected": 0, "found": 0, "first_ranks": []}
            )
            bucket["expected"] += 1
            if rank is not None:
                bucket["found"] += 1
                bucket["first_ranks"].append(rank)
    for bucket in by_type.values():
        bucket["recall_at_10"] = round(bucket["found"] / bucket["expected"], 4)
        first = bucket.pop("first_ranks")
        bucket["first_relevant_rank_mean"] = (
            round(sum(first) / len(first), 2) if first else None
        )
    return {
        "queries": len(rows),
        "scored_queries": len(scored),
        "recall_at_10": round(sum(recalls) / len(recalls), 4) if recalls else None,
        "first_relevant_rank_mean": (
            round(sum(first_ranks) / len(first_ranks), 2) if first_ranks else None
        ),
        "queries_with_misses": sum(1 for row in scored if row["missing"]),
        "result_types": dict(types),
        "by_type": by_type,
    }
