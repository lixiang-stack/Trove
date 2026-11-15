package dev.trove.reader

import org.junit.Assert.assertEquals
import org.junit.Test

class ReaderLocatorMappingTest {
    @Test
    fun hrefMapsToSpineIndexIgnoringFragments() {
        val order = listOf("OEBPS/chapter1.xhtml", "OEBPS/chapter2.xhtml")
        assertEquals(1, ReaderLocatorMapping.chapterIndexForHref("OEBPS/chapter2.xhtml#p3", order))
    }

    @Test
    fun unknownHrefFallsBackToFirstChapter() {
        assertEquals(
            0,
            ReaderLocatorMapping.chapterIndexForHref(
                "OEBPS/missing.xhtml",
                listOf("OEBPS/chapter1.xhtml"),
            ),
        )
    }

    @Test
    fun readiumLocatorKeepsLegacyAndEpubFields() {
        val locator = ReaderLocatorMapping.toBookLocator(
            chapterIndex = 2,
            paragraphIndex = 5,
            href = "OEBPS/chapter3.xhtml",
            progression = 0.4,
            totalProgression = 0.72,
        )
        assertEquals(2, locator.chapterIndex)
        assertEquals(5, locator.paragraphIndex)
        assertEquals(0.4, locator.scrollRatio, 0.0)
        assertEquals("OEBPS/chapter3.xhtml", locator.epubHref)
        assertEquals(0.4, locator.epubProgression ?: 0.0, 0.0)
        assertEquals(0.72, locator.epubTotalProgression ?: 0.0, 0.0)
    }
}
