package dev.trove.core.tags

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class TagNormalizerTest {
    @Test
    fun stripsHashAndTrailingPunctuation() {
        assertEquals("AI", normalizeTag("#AI，").name)
    }

    @Test
    fun englishPluralsUseHostNormalization() {
        val tag = normalizeTag("Videos")
        assertEquals("Videos", tag.name)
        assertEquals("video", tag.normalizedName)
    }

    @Test
    fun duplicateTagsAreDeduplicatedByNormalizedName() {
        val tags = normalizeTags(listOf("AI", "ai", "#AI"))
        assertEquals(listOf("AI"), tags.map { it.name })
    }

    @Test
    fun emptyAndLongTagsAreRejected() {
        assertTrue(runCatching { normalizeTag("#") }.exceptionOrNull() is InvalidTagException)
        assertTrue(
            runCatching { normalizeTag("x".repeat(65)) }.exceptionOrNull() is InvalidTagException
        )
    }
}
