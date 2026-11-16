package dev.trove.reader

import dev.trove.core.reading.BookLocator

object ReaderLocatorMapping {
    fun chapterIndexForHref(href: String, readingOrder: List<String>): Int {
        val target = href.substringBefore('#')
        val exact = readingOrder.indexOfFirst { it.substringBefore('#') == target }
        if (exact >= 0) return exact
        return readingOrder.indexOfFirst {
            it.substringBefore('#').endsWith(target.removePrefix("./"))
        }.takeIf { it >= 0 } ?: 0
    }

    fun toBookLocator(
        chapterIndex: Int,
        paragraphIndex: Int?,
        href: String,
        progression: Double?,
        totalProgression: Double?,
    ): BookLocator = BookLocator(
        chapterIndex = chapterIndex,
        paragraphIndex = paragraphIndex,
        scrollRatio = (progression ?: totalProgression ?: 0.0).coerceIn(0.0, 1.0),
        epubHref = href,
        epubProgression = progression?.coerceIn(0.0, 1.0),
        epubTotalProgression = totalProgression?.coerceIn(0.0, 1.0),
    )

    fun initialChapter(locator: BookLocator?, readingOrderSize: Int): Int {
        val index = locator?.chapterIndex ?: 0
        if (readingOrderSize <= 0) return 0
        return index.coerceIn(0, readingOrderSize - 1)
    }
}
