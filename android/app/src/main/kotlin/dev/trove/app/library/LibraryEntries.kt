package dev.trove.app.library

import dev.trove.core.library.LibraryItem

sealed interface LibraryEntry {
    val id: String
    val items: List<LibraryItem>

    val sortAddedAt: Long
        get() = items.maxOfOrNull { it.fetchedAt } ?: 0L

    val sortConsumedAt: Long
        get() = items.maxOfOrNull { it.lastConsumedAt ?: Long.MIN_VALUE } ?: Long.MIN_VALUE

    data class Single(val item: LibraryItem) : LibraryEntry {
        override val id: String get() = item.id
        override val items: List<LibraryItem> get() = listOf(item)
    }

    data class CollectionCard(
        val collectionId: String,
        val title: String,
        val platform: String,
        val author: String?,
        override val items: List<LibraryItem>,
    ) : LibraryEntry {
        override val id: String get() = collectionId

        val representative: LibraryItem get() = items.first()
        val coverItem: LibraryItem
            get() = items.firstOrNull { it.coverArtifact != null } ?: representative
        val episodeCount: Int get() = items.size
        val completedCount: Int get() = items.count { it.processingState == "completed" }
        val processingCount: Int get() = items.count {
            it.processingState !in setOf("completed", "failed", "cancelled", "queued")
        }
        val queuedCount: Int get() = items.count { it.processingState == "queued" }
        val failedCount: Int get() = items.count { it.processingState == "failed" }
        val finishedCount: Int get() = items.count { it.consumptionState == "finished" }
        val consumptionProgress: Float
            get() = if (episodeCount == 0) 0f else finishedCount.toFloat() / episodeCount
    }
}

fun List<LibraryItem>.toLibraryEntries(): List<LibraryEntry> {
    val collections = mutableMapOf<String, MutableList<LibraryItem>>()
    val singles = mutableListOf<LibraryEntry.Single>()
    for (item in this) {
        val collectionId = item.collectionId
        if (collectionId == null) {
            singles += LibraryEntry.Single(item)
        } else {
            collections.getOrPut(collectionId) { mutableListOf() } += item
        }
    }
    val cards = collections.map { (collectionId, collectionItems) ->
        val sorted = collectionItems.sortedWith(
            compareBy<LibraryItem> { it.collectionIndex ?: Int.MAX_VALUE }
                .thenBy { it.fetchedAt }
        )
        val first = sorted.first()
        LibraryEntry.CollectionCard(
            collectionId = collectionId,
            title = first.collectionTitle ?: "合集",
            platform = first.collectionPlatform ?: first.platform,
            author = first.author,
            items = sorted,
        )
    }
    return (singles + cards).sortedWith(
        compareByDescending<LibraryEntry> { it.sortAddedAt }.thenByDescending { it.id }
    )
}

fun applyLibraryEntryQuery(
    entries: List<LibraryEntry>,
    filters: LibraryFilters,
    sort: LibrarySort,
): List<LibraryEntry> {
    val filtered = entries.filter { entry ->
        (!filters.inbox || entry.items.any { it.isInbox }) &&
            (filters.type == null || entry.items.any { it.sourceType == filters.type }) &&
            (filters.consumption == null ||
                entry.items.any { it.consumptionState == filters.consumption }) &&
            (filters.tag == null || entry.items.any { filters.tag in it.tags }) &&
            (filters.source == null || entry.items.any { it.platform == filters.source })
    }
    val base = when (sort) {
        LibrarySort.RECENT_ADDED -> compareByDescending<LibraryEntry> { it.sortAddedAt }
            .thenByDescending { it.id }

        LibrarySort.RECENT_CONSUMED -> compareByDescending<LibraryEntry> { it.sortConsumedAt }
            .thenByDescending { it.sortAddedAt }
            .thenByDescending { it.id }
    }
    return filtered.sortedWith(continueFirst<LibraryEntry> { it.inProgressAt() }.then(base))
}

private fun LibraryEntry.inProgressAt(): Long? =
    items.filter { it.consumptionState == "in_progress" }
        .maxOfOrNull { it.lastConsumedAt ?: Long.MIN_VALUE }
