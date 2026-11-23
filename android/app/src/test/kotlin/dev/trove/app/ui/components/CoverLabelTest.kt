package dev.trove.app.ui.components

import dev.trove.core.library.LibraryItem
import org.junit.Assert.assertEquals
import org.junit.Test

class CoverLabelTest {
    @Test
    fun collectionEpisodeCoverUsesTitleInsteadOfIndex() {
        val title = "2025年曾仕强道德经功成不居高清版 全100讲 p03 第3集 无为而治"
        val item = item(
            title = title,
            collectionTitle = "2025年曾仕强道德经功成不居高清版 全100讲",
            collectionIndex = 3,
        )

        assertEquals("无为而治", coverLabel(item))
        assertEquals(
            "无为",
            coverText(title, item.collectionTitle, allowFullTitle = false),
        )
    }

    @Test
    fun standaloneCoverUsesTitleInitials() {
        val item = item(title = "采集：从链接到内容包")

        assertEquals("采集", coverLabel(item))
    }

    @Test
    fun smallLatinCoverUsesInitials() {
        val item = item(
            title = "Episode One",
            collectionTitle = "Fixture Collection",
            collectionIndex = 1,
        )

        assertEquals(
            "EO",
            coverText(item.title, item.collectionTitle, allowFullTitle = false),
        )
    }

    private fun item(
        title: String,
        collectionTitle: String? = null,
        collectionIndex: Int? = null,
    ) = LibraryItem(
        id = "item-1",
        version = 1,
        sourceType = "video_url",
        platform = "bilibili",
        collectionId = collectionTitle?.let { "collection-1" },
        collectionIndex = collectionIndex,
        collectionTitle = collectionTitle,
        collectionPlatform = collectionTitle?.let { "bilibili" },
        collectionSourceUrl = null,
        title = title,
        author = null,
        fetchedAt = 1,
        language = "zh",
        durationSec = 100.0,
        summary = null,
        tags = emptyList(),
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
