from __future__ import annotations

import pytest

from trove.evaluation import (
    QueryExpectation,
    load_expectations,
    score_query,
    summarize_scores,
)


def _result(item_id: str, title: str, source_type: str = "local_audio"):
    return {
        "item": {"id": item_id, "title": title, "source_type": source_type},
        "evidence": [{"snippet": f"{title} snippet"}],
    }


def test_load_expectations_validates_shape():
    rows = load_expectations(
        {"queries": [{"query": "记忆", "expected": ["a"]}, {"query": "explore"}]}
    )
    assert rows[0] == QueryExpectation("记忆", ["a"])
    assert rows[1].expected == []
    with pytest.raises(ValueError):
        load_expectations({"queries": []})
    with pytest.raises(ValueError):
        load_expectations({"queries": [{"query": "x", "expected": "a"}]})


def test_score_query_counts_misses_and_rank():
    expectation = QueryExpectation("记忆", ["a", "b", "c"])
    results = [_result("x", "X"), _result("b", "B"), _result("a", "A")]

    row = score_query(expectation, results)

    assert row["ranks"] == {"a": 3, "b": 2, "c": None}
    assert row["recall_at_10"] == pytest.approx(2 / 3)
    assert row["first_relevant_rank"] == 2
    assert row["missing"] == ["c"]


def test_score_query_exploratory_has_no_recall():
    row = score_query(QueryExpectation("explore", []), [_result("a", "A")])
    assert row["recall_at_10"] is None
    assert row["first_relevant_rank"] is None


def test_summarize_scores_aggregates_types_and_misses():
    rows = [
        score_query(
            QueryExpectation("memory", ["a", "b"]),
            [_result("a", "A", "video_url"), _result("x", "X", "book")],
        ),
        score_query(
            QueryExpectation("explore", []),
            [_result("y", "Y", "podcast_episode")],
        ),
    ]
    summary = summarize_scores(rows)
    assert summary["queries"] == 2
    assert summary["scored_queries"] == 1
    assert summary["recall_at_10"] == 0.5
    assert summary["queries_with_misses"] == 1
    assert summary["result_types"] == {
        "video_url": 1,
        "book": 1,
        "podcast_episode": 1,
    }
    assert summary["by_type"]["video_url"]["recall_at_10"] == 1.0
    assert summary["by_type"]["unknown"]["recall_at_10"] == 0.0
