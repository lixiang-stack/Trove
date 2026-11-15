#!/usr/bin/env python3
"""Seed a throwaway TROVE_HOME for Android UI/acceptance work."""

# ruff: noqa: E402
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from trove.clock import utc_ms
from trove.composition import build_runtime
from trove.config import Config
from trove.content_package import ArtifactKind, TranscriptDocument, sha256_file
from trove.db.engine import upgrade_database
from trove.db.models import Artifact, Item, ItemTag, Run, RunStep, Tag
from trove.domain.tags import normalize_tag

FIXTURES = REPO / "tests" / "fixtures"
PASSWORD = "acceptance-pass"


def add_item(
    runtime,
    config: Config,
    *,
    title: str,
    source_key: str,
    audio: Path,
    source_type: str = "local_audio",
    platform: str = "local",
    tags: list[str] | None = None,
    consumption: str = "unstarted",
    position: float = 0.0,
    run_state: str = "completed",
    with_transcript: bool = True,
) -> str:
    bundle, _ = runtime.library.create_item(
        source_key=source_key,
        source_type=source_type,
        platform=platform,
        title=title,
        author="验收作者",
        language="zh",
        duration_sec=20.0,
    )
    item_id = bundle.item.id
    installed_audio = runtime.package.copy_artifact(
        item_id, ArtifactKind.AUDIO, audio, extension=".m4a", mime="audio/mp4"
    )
    transcript_doc = TranscriptDocument.from_json(
        json.loads((FIXTURES / "transcript.json").read_text(encoding="utf-8"))
    )
    transcript_path = runtime.package.write_transcript(item_id, transcript_doc)
    with runtime.sessions() as session:
        session.add(
            Artifact(
                item_id=item_id,
                kind="audio",
                path=installed_audio.relative_path,
                sha256=installed_audio.sha256,
                size=installed_audio.size,
                mime=installed_audio.mime,
                duration_sec=20.0,
            )
        )
        if with_transcript:
            session.add(
                Artifact(
                    item_id=item_id,
                    kind="transcript",
                    path="transcript.json",
                    sha256=sha256_file(transcript_path),
                    size=transcript_path.stat().st_size,
                    mime="application/json",
                )
            )
        item = session.get(Item, item_id)
        item.summary = f"{title} 的验收摘要。"
        item.consumption_state = consumption
        item.audio_position_sec = position
        item.last_consumed_at = utc_ms() if consumption != "unstarted" or position > 0 else None
        item.updated_at = utc_ms()
        run = Run(
            id=f"run-{item_id[:8]}",
            item_id=item_id,
            state=run_state,
            created_at=utc_ms(),
            started_at=utc_ms(),
            finished_at=utc_ms() if run_state in {"completed", "failed", "cancelled"} else None,
            error_code="download.network" if run_state == "failed" else None,
            error_message="Network error" if run_state == "failed" else None,
        )
        session.add(run)
        if run_state in {"completed", "failed", "cancelled"}:
            session.add(
                RunStep(
                    run_id=run.id,
                    stage="indexing",
                    state="completed",
                    attempt=1,
                    started_at=utc_ms(),
                    finished_at=utc_ms(),
                )
            )
        for raw in tags or []:
            display, normalized = normalize_tag(raw)
            tag = session.query(Tag).filter_by(normalized_name=normalized).first()
            if tag is None:
                tag = Tag(name=display, normalized_name=normalized)
                session.add(tag)
                session.flush()
            session.add(ItemTag(item_id=item_id, tag_id=tag.id, source="user"))
        session.commit()
    return item_id


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: seed_acceptance.py <TROVE_HOME>", file=sys.stderr)
        return 2
    home = Path(sys.argv[1]).expanduser().resolve()
    config = Config(home=home)
    config.ensure_layout()
    config.set_password(PASSWORD)
    upgrade_database(config)
    runtime = build_runtime(config)

    ids = [
        add_item(
            runtime,
            config,
            title="记忆是智能体的瓶颈",
            source_key="acceptance:memory",
            audio=FIXTURES / "long.m4a",
            tags=["AI", "记忆"],
            consumption="in_progress",
            position=8.0,
        ),
        add_item(
            runtime,
            config,
            title="上下文窗口的边界",
            source_key="acceptance:context",
            audio=FIXTURES / "short.m4a",
            source_type="podcast_episode",
            platform="podcast",
            tags=["AI"],
            consumption="finished",
            position=20.0,
        ),
        add_item(
            runtime,
            config,
            title="处理中的 Item",
            source_key="acceptance:processing",
            audio=FIXTURES / "short.m4a",
            tags=["Inbox"],
            run_state="transcribing",
        ),
        add_item(
            runtime,
            config,
            title="失败的 Item",
            source_key="acceptance:failed",
            audio=FIXTURES / "short.m4a",
            tags=["Inbox"],
            run_state="failed",
        ),
    ]
    print(f"home={home}")
    print(f"password={PASSWORD}")
    print("items=" + ",".join(ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
