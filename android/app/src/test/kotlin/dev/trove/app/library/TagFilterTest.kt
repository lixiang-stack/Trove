package dev.trove.app.library

import dev.trove.core.library.LibraryItem
import org.junit.Assert.assertEquals
import org.junit.Test

class TagFilterTest {
    @Test
    fun tagOptionsCountEachTagOncePerItemAndSortBySharedUsage() {
        val items = listOf(
            item("a", tags = listOf("道德经", "修身", "道德经")),
            item("b", tags = listOf("道德经", "道家哲学")),
            item("c", tags = listOf("道德经")),
        )

        val options = tagOptions(items)

        assertEquals("道德经", options.first().name)
        assertEquals(3, options.first().count)
        assertEquals(
            listOf("修身", "道家哲学"),
            options.drop(1).map { it.name }.sorted(),
        )
    }

    private fun item(id: String, tags: List<String>) = LibraryItem(
        id = id,
        version = 1,
        sourceType = "video_url",
        platform = "bilibili",
        collectionId = null,
        collectionIndex = null,
        collectionTitle = null,
        collectionPlatform = null,
        collectionSourceUrl = null,
        title = "Item $id",
        author = null,
        fetchedAt = 1,
        language = "zh",
        durationSec = 100.0,
        summary = null,
        tags = tags,
        processingState = "completed",
        errorCode = null,
        errorMessage = null,
        consumptionState = "unstarted",
        audioPositionSec = 0.0,
        bookLocator = null,
        lastConsumedAt = null,
        hasAudio = true,
        hasBook = false,
        artifacts = emptyList(),
    )
}
