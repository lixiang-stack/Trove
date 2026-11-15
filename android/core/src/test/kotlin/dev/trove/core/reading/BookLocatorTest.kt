package dev.trove.core.reading

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BookLocatorTest {
    @Test
    fun legacyLocatorRoundTripsWithoutSchemaFields() {
        val locator = BookLocator(chapterIndex = 2, paragraphIndex = 5, scrollRatio = 0.42)
        val raw = locator.toJson()
        assertFalse(raw.contains("schema"))
        assertEquals(locator, BookLocator.parse(raw))
    }

    @Test
    fun schemaTwoLocatorKeepsEpubFields() {
        val locator = BookLocator(
            chapterIndex = 1,
            paragraphIndex = 3,
            scrollRatio = 0.5,
            epubHref = "OEBPS/chapter2.xhtml",
            epubProgression = 0.25,
            epubTotalProgression = 0.6,
        )
        val raw = locator.toJson()
        assertTrue(raw.contains("\"schema\":2"))
        assertEquals(locator, BookLocator.parse(raw))
    }

    @Test
    fun invalidLocatorsAreRejected() {
        assertNull(BookLocator.parse("not json"))
        assertNull(BookLocator.parse("{\"schema\":3,\"chapter_index\":0}"))
        assertNull(BookLocator.parse("{\"chapter_index\":-1}"))
        assertNull(BookLocator.parse("{\"chapter_index\":0,\"epub_progression\":2}"))
    }

    @Test
    fun fractionPrefersTotalProgression() {
        val locator = BookLocator(
            chapterIndex = 0,
            scrollRatio = 0.1,
            epubHref = "chapter.xhtml",
            epubProgression = 0.2,
            epubTotalProgression = 0.7,
        )
        assertEquals(0.7, locator.fraction, 0.0)
    }
}
