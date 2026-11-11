#!/usr/bin/env python3
"""Run pre-registered search queries against a running Trove Host.

The queries file is JSON:

{
  "queries": [
    {"query": "记忆", "expected": ["<item-id>"]},
    {"query": "一个探索式查询", "expected": []}
  ]
}

`expected` is a list of Item ids judged relevant before seeing results. The script
prints top-10 results with evidence and computes recall@10 plus first relevant rank
for queries that declare expected Items. It never edits the query list.
"""

from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from trove.evaluation import load_expectations, score_query, summarize_scores  # noqa: E402


def _opener(base_url: str, password: str) -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/auth/login",
        data=json.dumps({"password": password}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener.open(request, timeout=30).read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Login failed: HTTP {exc.code}") from exc
    return opener


def _get_json(opener: urllib.request.OpenerDirector, url: str) -> dict:
    try:
        with opener.open(url, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Request failed: HTTP {exc.code} {url}") from exc


def _markdown(rows: list[dict], expectations) -> str:
    summary = summarize_scores(rows)
    lines = [
        "# Search evaluation",
        "",
        f"- Queries: {summary['queries']}",
        f"- Scored queries: {summary['scored_queries']}",
        f"- recall@10: {summary['recall_at_10']}",
        f"- Mean first relevant rank: {summary['first_relevant_rank_mean']}",
        f"- Queries with misses: {summary['queries_with_misses']}",
        f"- Result types: {summary['result_types']}",
        "",
        "## By content type",
        "",
        "| Type | Expected | Found | recall@10 | Mean first rank |",
        "| ---- | -------: | ----: | --------- | --------------: |",
    ]
    for kind, bucket in summary["by_type"].items():
        lines.append(
            f"| {kind} | {bucket['expected']} | {bucket['found']} | "
            f"{bucket['recall_at_10']} | {bucket['first_relevant_rank_mean']} |"
        )
    lines.append("")
    for row, expectation in zip(rows, expectations, strict=True):
        lines.append(f"## {row['query']}")
        lines.append("")
        lines.append(f"- Expected: {', '.join(row['expected']) or 'none (exploratory)'}")
        lines.append(f"- recall@10: {row['recall_at_10']}")
        lines.append(f"- First relevant rank: {row['first_relevant_rank']}")
        if row["missing"]:
            lines.append(f"- Missed: {', '.join(row['missing'])}")
        lines.append("")
        if not row["results"]:
            lines.append("No results.")
            lines.append("")
            continue
        lines.append("| Rank | Item | Type | Evidence |")
        lines.append("| ---: | ---- | ---- | -------- |")
        for rank, result in enumerate(row["results"], 1):
            item = result["item"]
            evidence = (result.get("evidence") or [{}])[0]
            snippet = str(evidence.get("snippet") or "").replace("|", "\\|")
            marker = " ✓" if item["id"] in expectation.expected else ""
            lines.append(
                f"| {rank} | {item['title']}{marker}<br>`{item['id']}` | "
                f"{item.get('source_type_label') or item.get('source_type')} | {snippet} |"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--queries", required=True, help="pre-registered JSON file")
    parser.add_argument("--out", default=None, help="write Markdown to this file")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--password-env", default="TROVE_EVAL_PASSWORD")
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args(argv)

    password = os.environ.get(args.password_env)
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    if not password:
        password = getpass.getpass("Trove password: ")

    try:
        expectations = load_expectations(
            json.loads(Path(args.queries).read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Invalid queries file: {exc}", file=sys.stderr)
        return 2

    opener = _opener(args.base_url, password)
    rows = []
    for expectation in expectations:
        query = urllib.parse.quote(expectation.query)
        payload = _get_json(
            opener,
            f"{args.base_url.rstrip('/')}/api/search?q={query}&limit=10",
        )
        row = score_query(expectation, payload.get("results") or [])
        row["results"] = payload.get("results") or []
        rows.append(row)

    if args.as_json:
        output = json.dumps(
            {"summary": summarize_scores(rows), "queries": rows},
            ensure_ascii=False,
            indent=2,
        )
    else:
        output = _markdown(rows, expectations)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
