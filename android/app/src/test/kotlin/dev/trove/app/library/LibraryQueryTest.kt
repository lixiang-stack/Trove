package dev.trove.app.library

import dev.trove.app.collection.sortCollectionEpisodes
import dev.trove.core.library.LibraryItem
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LibraryQueryTest {
    @Test
    fun recentAddedSortsByFetchedAtDescending() {
        val items = listOf(
            item("a", fetchedAt = 10),
            item("b", fetchedAt = 30),
            item("c", fetchedAt = 20),
        )
        assertEquals(
            listOf("b", "c", "a"),
            applyLibraryQuery(items, LibraryFilters(), LibrarySort.RECENT_ADDED).map { it.id },
        )
    }

    @Test
    fun recentConsumedSortsByLastConsumedWithUnconsumedLast() {
        val items = listOf(
            item("a", lastConsumedAt = 10),
            item("b", lastConsumedAt = null),
            item("c", lastConsumedAt = 30),
        )
        assertEquals(
            listOf("c", "a", "b"),
            applyLibraryQuery(items, LibraryFilters(), LibrarySort.RECENT_CONSUMED).map { it.id },
        )
    }

    @Test
    fun inProgressEntriesComeFirstWithMostRecentContinueFirst() {
        val entries = listOf(
            item("newest", fetchedAt = 30),
            item("older-progress", fetchedAt = 10, lastConsumedAt = 5, consumptionState = "in_progress"),
            item("last-continued", fetchedAt = 20, lastConsumedAt = 10, consumptionState = "in_progress"),
        ).toLibraryEntries()

        assertEquals(
            listOf("last-continued", "older-progress", "newest"),
            applyLibraryEntryQuery(entries, LibraryFilters(), LibrarySort.RECENT_ADDED).map { it.id },
        )
    }

    @Test
    fun inboxFiltersProcessingAndFailedItems() {
        val items = listOf(
            item("ready", processingState = "completed"),
            item("processing", processingState = "transcribing"),
            item("failed", processingState = "failed"),
            item("cancelled", processingState = "cancelled"),
        )
        assertEquals(
            listOf("failed", "processing"),
            applyLibraryQuery(
                items,
                LibraryFilters(inbox = true),
                LibrarySort.RECENT_ADDED,
            ).map { it.id }.sorted(),
        )
    }

    @Test
    fun filtersComposeByTypeConsumptionTagAndSource() {
        val items = listOf(
            item(
                "match",
                sourceType = "video_url",
                platform = "youtube",
                consumptionState = "in_progress",
                tags = listOf("AI", "记忆"),
            ),
            item(
                "wrong-tag",
                sourceType = "video_url",
                platform = "youtube",
                consumptionState = "in_progress",
                tags = listOf("AI"),
            ),
            item(
                "wrong-source",
                sourceType = "video_url",
                platform = "bilibili",
                consumptionState = "in_progress",
                tags = listOf("AI", "记忆"),
            ),
            item(
                "wrong-state",
                sourceType = "video_url",
                platform = "youtube",
                consumptionState = "finished",
                tags = listOf("AI", "记忆"),
            ),
        )
        val filters = LibraryFilters(
            type = "video_url",
            consumption = "in_progress",
            tag = "记忆",
            source = "youtube",
        )
        assertEquals(
            listOf("match"),
            applyLibraryQuery(items, filters, LibrarySort.RECENT_ADDED).map { it.id },
        )
        assertEquals(4, filters.activeCount)
    }

    @Test
    fun thousandItemQueryStaysResponsive() {
        val items = List(1_000) { index ->
            item(
                "item-$index",
                fetchedAt = index.toLong(),
                tags = listOf(if (index % 2 == 0) "even" else "odd"),
                sourceType = if (index % 3 == 0) "podcast_episode" else "video_url",
            )
        }
        val start = System.nanoTime()
        val result = applyLibraryQuery(
            items,
            LibraryFilters(type = "podcast_episode", tag = "even"),
            LibrarySort.RECENT_ADDED,
        )
        val elapsedMs = (System.nanoTime() - start) / 1_000_000
        assertTrue(result.isNotEmpty())
        assertTrue("query took ${elapsedMs}ms", elapsedMs < 2_000)
    }

    @Test
    fun collectionEpisodesPutMostRecentlyConsumedFirstThenUpstreamOrder() {
        val episodes = listOf(
            item("episode-3", collectionId = "c1", collectionIndex = 3),
            item(
                "episode-2",
                collectionId = "c1",
                collectionIndex = 2,
                lastConsumedAt = 20,
                consumptionState = "in_progress",
            ),
            item(
                "episode-1",
                collectionId = "c1",
                collectionIndex = 1,
                lastConsumedAt = 10,
                consumptionState = "finished",
            ),
            item("episode-4", collectionId = "c1", collectionIndex = 4),
        )

        assertEquals(
            listOf("episode-2", "episode-1", "episode-3", "episode-4"),
            sortCollectionEpisodes(episodes).map { it.id },
        )
    }

    @Test
    fun collectionsGroupChildrenAndFiltersMatchAnyChild() {
        val items = listOf(
            item(
                "episode-2",
                fetchedAt = 20,
                processingState = "completed",
                consumptionState = "in_progress",
                collectionId = "c1",
                collectionIndex = 2,
                collectionTitle = "Collection One",
            ),
            item(
                "episode-1",
                fetchedAt = 10,
                processingState = "transcribing",
                collectionId = "c1",
                collectionIndex = 1,
                collectionTitle = "Collection One",
            ),
            item("standalone", fetchedAt = 30),
        )
        val entries = items.toLibraryEntries()
        assertEquals(2, entries.size)
        val collection = entries.filterIsInstance<LibraryEntry.CollectionCard>().single()
        assertEquals("Collection One", collection.title)
        assertEquals(listOf("episode-1", "episode-2"), collection.items.map { it.id })
        assertEquals(2, collection.episodeCount)
        assertEquals(1, collection.completedCount)
        assertEquals(1, collection.processingCount)

        val inbox = applyLibraryEntryQuery(entries, LibraryFilters(inbox = true), LibrarySort.RECENT_ADDED)
        assertEquals(listOf("c1"), inbox.map { it.id })

        val inProgress = applyLibraryEntryQuery(
            entries,
            LibraryFilters(consumption = "in_progress"),
            LibrarySort.RECENT_ADDED,
        )
        assertEquals(listOf("c1"), inProgress.map { it.id })
    }

    private fun item(
        id: String,
        fetchedAt: Long = 1,
        lastConsumedAt: Long? = null,
        processingState: String = "completed",
        consumptionState: String = "unstarted",
        sourceType: String = "video_url",
        platform: String = "youtube",
        tags: List<String> = emptyList(),
        collectionId: String? = null,
        collectionIndex: Int? = null,
        collectionTitle: String? = null,
    ) = LibraryItem(
        id = id,
        version = 1,
        sourceType = sourceType,
        platform = platform,
        collectionId = collectionId,
        collectionIndex = collectionIndex,
        collectionTitle = collectionTitle,
        collectionPlatform = if (collectionId != null) "youtube" else null,
        collectionSourceUrl = null,
        title = "Item $id",
        author = null,
        fetchedAt = fetchedAt,
        language = "zh",
        durationSec = 100.0,
        summary = null,
        tags = tags,
        processingState = processingState,
        errorCode = null,
        errorMessage = null,
        consumptionState = consumptionState,
        audioPositionSec = 0.0,
        bookLocator = null,
        lastConsumedAt = lastConsumedAt,
        hasAudio = true,
        hasBook = false,
        artifacts = emptyList(),
    )
}
