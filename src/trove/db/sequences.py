"""Server-assigned sync sequences and change tracking.

Every persistent content change bumps the Item version and content sequence;
state-only changes bump only the state sequence. Tracking lives here so that
new write paths cannot forget to advance the cursor visible to clients.
"""

from __future__ import annotations

import uuid

from sqlalchemy import event as sa_event
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql import update

from trove.db.models import Artifact, Item, ItemTag, Run, SyncSequence

STATE_FIELDS = frozenset(
    {"audio_position_sec", "book_locator", "consumption_state", "last_consumed_at"}
)
CONTENT_EXCLUDED = frozenset(
    {"updated_at", "version", "content_seq", "state_seq"}
)
RUN_CONTENT_FIELDS = frozenset(
    {
        "state",
        "current_stage",
        "error_code",
        "error_message",
        "cancel_requested_at",
        "finished_at",
    }
)


def next_sequence(session: Session) -> int:
    value = session.execute(
        update(SyncSequence)
        .where(SyncSequence.id == 1)
        .values(value=SyncSequence.value + 1)
        .returning(SyncSequence.value)
    ).scalar_one_or_none()
    if value is None:
        raise RuntimeError("sync_sequence is missing; run database migrations")
    return int(value)


def sequence_epoch(session: Session) -> str:
    epoch = session.execute(
        select(SyncSequence.epoch).where(SyncSequence.id == 1)
    ).scalar_one_or_none()
    if epoch is None:
        raise RuntimeError("sync_sequence is missing; run database migrations")
    return str(epoch)


def reset_epoch(session: Session) -> str:
    epoch = str(uuid.uuid4())
    session.execute(
        update(SyncSequence).where(SyncSequence.id == 1).values(epoch=epoch)
    )
    session.commit()
    return epoch


def install_sync_tracking(sessions: sessionmaker[Session]) -> None:
    sa_event.listen(sessions, "before_flush", _track_changes)


def _track_changes(session: Session, _flush_context, _instances) -> None:
    content: set[str] = set()
    state: set[str] = set()
    new_items: dict[str, Item] = {}
    _collect_new(session, content, new_items)
    _collect_dirty(session, content, state)
    _collect_deleted(session, content)
    deleted_items = {obj.id for obj in session.deleted if isinstance(obj, Item)}

    for new_item in new_items.values():
        new_item.version = 1
        new_item.content_seq = next_sequence(session)
        new_item.state_seq = next_sequence(session)

    for item_id in content | state:
        if item_id in new_items or item_id in deleted_items:
            continue
        item = session.get(Item, item_id)
        if item is None:
            continue
        if item_id in content:
            item.version += 1
            item.content_seq = next_sequence(session)
        if item_id in state:
            item.state_seq = next_sequence(session)


def _collect_new(
    session: Session, content: set[str], new_items: dict[str, Item]
) -> None:
    for obj in session.new:
        if isinstance(obj, Item):
            new_items[obj.id] = obj
        elif isinstance(obj, (Artifact, ItemTag, Run)):
            content.add(obj.item_id)


def _collect_dirty(session: Session, content: set[str], state: set[str]) -> None:
    for obj in session.dirty:
        if isinstance(obj, Item):
            changed = {
                attr.key
                for attr in inspect(obj).attrs
                if attr.key not in CONTENT_EXCLUDED and attr.history.has_changes()
            }
            if changed & STATE_FIELDS:
                state.add(obj.id)
            if changed - STATE_FIELDS:
                content.add(obj.id)
        elif isinstance(obj, Run) and any(
            inspect(obj).attrs[key].history.has_changes()
            for key in RUN_CONTENT_FIELDS
        ):
            content.add(obj.item_id)


def _collect_deleted(session: Session, content: set[str]) -> None:
    for obj in session.deleted:
        if isinstance(obj, (Artifact, ItemTag, Run)):
            content.add(obj.item_id)
