package dev.trove.app.library

import dev.trove.core.library.LibraryItem

enum class LibrarySort {
    RECENT_ADDED,
    RECENT_CONSUMED,
}

data class LibraryFilters(
    val inbox: Boolean = false,
    val type: String? = null,
    val consumption: String? = null,
    val tag: String? = null,
    val source: String? = null,
) {
    val activeCount: Int
        get() = listOfNotNull(
            type,
            consumption,
            tag,
            source,
        ).size + if (inbox) 1 else 0

    val hasAny: Boolean get() = inbox || activeCount > 0
}

data class LibraryFilterOptions(
    val types: List<String>,
    val consumptions: List<String>,
    val tags: List<String>,
    val sources: List<String>,
)

fun filterOptions(items: List<LibraryItem>): LibraryFilterOptions = LibraryFilterOptions(
    types = items.map { it.sourceType }.distinct().sorted(),
    consumptions = items.map { it.consumptionState }.distinct().sorted(),
    tags = items.flatMap { it.tags }.distinct().sorted(),
    sources = items.map { it.platform }.distinct().sorted(),
)

fun applyLibraryQuery(
    items: List<LibraryItem>,
    filters: LibraryFilters,
    sort: LibrarySort,
): List<LibraryItem> {
    val filtered = items.filter { item ->
        (!filters.inbox || item.isInbox) &&
            (filters.type == null || item.sourceType == filters.type) &&
            (filters.consumption == null || item.consumptionState == filters.consumption) &&
            (filters.tag == null || filters.tag in item.tags) &&
            (filters.source == null || item.platform == filters.source)
    }
    val base = when (sort) {
        LibrarySort.RECENT_ADDED -> compareByDescending<LibraryItem> { it.fetchedAt }
            .thenByDescending { it.id }

        LibrarySort.RECENT_CONSUMED -> compareByDescending<LibraryItem> {
            it.lastConsumedAt ?: Long.MIN_VALUE
        }.thenByDescending { it.fetchedAt }
            .thenByDescending { it.id }
    }
    return filtered.sortedWith(continueFirst<LibraryItem> { it.inProgressAt() }.then(base))
}

private fun LibraryItem.inProgressAt(): Long? =
    if (consumptionState == "in_progress") lastConsumedAt ?: Long.MIN_VALUE else null

internal fun <T> continueFirst(inProgressAt: (T) -> Long?): Comparator<T> =
    compareByDescending<T> { inProgressAt(it) != null }
        .thenByDescending { inProgressAt(it) ?: Long.MIN_VALUE }
