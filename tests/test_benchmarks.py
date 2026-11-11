from __future__ import annotations

import json

from trove.benchmarks import percentile, read_queries, run_search_benchmark, summarize


class FakeSearch:
    def __init__(self):
        self.calls = []

    def search(self, query, *, limit):
        self.calls.append((query, limit))
        return [query] * min(2, limit)

    def index_status(self):
        return type("Status", (), {"total_rows": 42})()


class FakeConfig:
    def __init__(self, db_path):
        self.db_path = db_path


class FakeRuntime:
    def __init__(self, db_path):
        self.search = FakeSearch()
        self.config = FakeConfig(db_path)


def test_percentiles_and_summary():
    values = [1.0, 2.0, 3.0, 4.0, 100.0]
    assert percentile(values, 0.5) == 3.0
    assert percentile(values, 0.95) == 100.0
    summary = summarize(values)
    assert summary["count"] == 5
    assert summary["min_ms"] == 1.0
    assert summary["max_ms"] == 100.0
    assert summary["p95_ms"] == 100.0


def test_read_queries_ignores_comments_and_blank_lines(tmp_path):
    path = tmp_path / "queries.txt"
    path.write_text("# pre-registered\n记忆\n\n智能体\n", encoding="utf-8")
    assert read_queries(path) == ["记忆", "智能体"]


def test_search_benchmark_records_every_query(tmp_path):
    database = tmp_path / "trove.db"
    database.write_bytes(b"db")
    runtime = FakeRuntime(database)
    payload = run_search_benchmark(runtime, ["记忆", "智能体"], repeat=2, limit=5)
    assert payload["queries"] == 2
    assert payload["summary"]["count"] == 4
    assert payload["index_rows"] == 42
    assert payload["database_bytes"] == 2
    assert [row["query"] for row in payload["results"]] == ["记忆", "智能体"]
    assert runtime.search.calls == [
        ("记忆", 5),
        ("记忆", 5),
        ("智能体", 5),
        ("智能体", 5),
    ]


def test_seed_library_creates_searchable_items(tmp_path):
    from trove.benchmarks import seed_library
    from trove.composition import build_runtime
    from trove.config import Config
    from trove.db.engine import upgrade_database

    config = Config(home=tmp_path / "seed-home")
    config.ensure_layout()
    upgrade_database(config)

    assert seed_library(config, 6) == 6
    runtime = build_runtime(config)
    assert runtime.search.search("人工智能", limit=20)
    assert len(runtime.library.list_items()) == 6


def test_bench_search_cli_uses_the_library(host, tmp_path, monkeypatch, capsys):
    from trove.cli import main

    from .conftest import seed_item

    bundle = seed_item(host, title="Benchmark item")
    host.runtime.search_index.index_item(bundle.item.id)
    queries = tmp_path / "queries.txt"
    queries.write_text("Benchmark\n", encoding="utf-8")
    monkeypatch.setenv("TROVE_HOME", str(host.config.home))

    code = main(
        [
            "bench",
            "search",
            "--queries",
            str(queries),
            "--repeat",
            "1",
            "--json",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["queries"] == 1
    assert payload["results"][0]["results"] == 1
