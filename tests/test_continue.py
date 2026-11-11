from __future__ import annotations

from sqlalchemy import text

from .conftest import seed_item


def _seed_book(host, *, title: str, chapter: int = 0, locator: str | None = None):
    from trove.db.models import BookChapter, BookParagraph

    bundle = seed_item(
        host,
        title=title,
        source_type="epub",
        with_audio=False,
        duration=0.0,
        run_state="completed",
    )
    with host.runtime.sessions() as session:
        session.add(
            BookChapter(
                item_id=bundle.item.id,
                chapter_index=chapter,
                title=f"Chapter {chapter + 1}",
                html=f"<p>{title} text</p>",
                text=f"{title} text",
            )
        )
        session.add(
            BookParagraph(
                item_id=bundle.item.id,
                chapter_index=chapter,
                paragraph_index=0,
                text=f"{title} text",
            )
        )
        session.commit()
    if locator is not None:
        with host.runtime.sessions() as session:
            session.execute(
                text(
                    "UPDATE items SET book_locator = :locator, consumption_state = 'in_progress' "
                    "WHERE id = :item_id"
                ),
                {"locator": locator, "item_id": bundle.item.id},
            )
            session.commit()
    return bundle


def _touch(host, item_id: str, updated_at: int) -> None:
    with host.runtime.sessions() as session:
        session.execute(
            text(
                "UPDATE items SET updated_at = :updated_at, last_consumed_at = :updated_at "
                "WHERE id = :item_id"
            ),
            {"updated_at": updated_at, "item_id": item_id},
        )
        session.commit()


def test_continue_lists_recent_audio_and_books_and_excludes_finished(host):
    audio = seed_item(
        host, title="Continue audio", consumption_state="in_progress", position=30.0, duration=100.0
    )
    book = _seed_book(
        host,
        title="Continue book",
        locator='{"chapter_index":0,"paragraph_index":0,"scroll_ratio":0.25}',
    )
    finished = seed_item(
        host,
        title="Finished audio",
        consumption_state="finished",
        position=100.0,
        duration=100.0,
    )
    _touch(host, audio.item.id, 1_000)
    _touch(host, book.item.id, 2_000)
    _touch(host, finished.item.id, 3_000)
    host.login()

    page = host.client.get("/continue")
    assert page.status_code == 200
    assert "Continue audio" in page.text
    assert "Continue book" in page.text
    assert "Finished audio" not in page.text
    assert page.text.index("Continue book") < page.text.index("Continue audio")
    assert f'href="/items/{audio.item.id}/listen"' in page.text
    assert f'href="/items/{book.item.id}/read"' in page.text
    assert "继续听" in page.text
    assert "继续读" in page.text


def test_continue_navigation_is_visible_and_empty_state_links_to_library(host):
    host.login()
    page = host.client.get("/continue")
    assert "还没有进行中的内容" in page.text
    assert 'href="/library"' in page.text
    assert 'href="/add"' in page.text
    library = host.client.get("/library")
    assert 'href="/continue"' in library.text
    assert library.text.count('href="/continue"') >= 2


def test_continue_ordering_ignores_tag_edits(host):
    older = seed_item(
        host,
        title="Older continue",
        consumption_state="in_progress",
        position=10.0,
        duration=100.0,
    )
    newer = seed_item(
        host,
        title="Newer continue",
        consumption_state="in_progress",
        position=10.0,
        duration=100.0,
    )
    _touch(host, older.item.id, 1_000)
    _touch(host, newer.item.id, 2_000)
    host.login()
    host.client.post(f"/api/items/{older.item.id}/tags", json={"tag": "later edit"})
    page = host.client.get("/continue")
    assert page.text.index("Newer continue") < page.text.index("Older continue")


def test_continue_book_with_stale_chapter_falls_back_to_the_first_chapter(host):
    book = _seed_book(
        host,
        title="Stale locator",
        chapter=0,
        locator='{"chapter_index":9,"paragraph_index":0,"scroll_ratio":0.0}',
    )
    host.login()
    page = host.client.get(f"/items/{book.item.id}/read")
    assert page.status_code == 200
    assert "Stale locator text" in page.text


def test_continue_audio_link_restores_the_saved_position(host):
    audio = seed_item(
        host,
        title="Resume audio",
        consumption_state="in_progress",
        position=42.0,
        duration=100.0,
    )
    host.login()
    page = host.client.get(f"/items/{audio.item.id}/listen")
    assert '"position": 42.0' in page.text
    assert f"/api/items/{audio.item.id}/audio" in page.text
