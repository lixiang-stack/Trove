package dev.trove.app.search

import dev.trove.core.network.ItemDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SearchMapperTest {
    private val item = ItemDto(id = "item-1", title = "Item").toLibraryItem()

    @Test
    fun anchorSkipsSummaryAndUsesFirstBookOrTranscriptEvidence() {
        val result = SearchUiResult(
            item = item,
            evidence = listOf(
                SearchUiEvidence("summary", "summary", "Summary", "summary"),
                SearchUiEvidence(
                    "book",
                    "2:5",
                    "Book · 2:5",
                    "paragraph",
                    chapterIndex = 2,
                    paragraphIndex = 5,
                ),
            ),
        )

        assertEquals("book", result.anchor?.docKind)
        assertEquals(2, result.anchor?.chapterIndex)
    }

    @Test
    fun metadataOnlyResultHasNoAnchor() {
        val result = SearchUiResult(
            item = item,
            evidence = listOf(SearchUiEvidence("title", "title", "Title", "title")),
        )

        assertNull(result.anchor)
    }
}
