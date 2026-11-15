package dev.trove.core.search

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SearchQueryTest {
    private fun resource(name: String): String =
        checkNotNull(javaClass.getResource("/$name")) { "missing fixture $name" }.readText()

    @Test
    fun chineseTextIsIndexedAsBigrams() {
        val fixture = kotlinx.serialization.json.Json.parseToJsonElement(
            resource("search-query.json")
        ) as kotlinx.serialization.json.JsonObject
        val query = fixture["query"]!!.toString().trim('"')
        val tokens = (fixture["tokens"] as kotlinx.serialization.json.JsonArray)
            .map { it.toString().trim('"') }
        assertEquals(tokens, documentTokens(query))
        assertEquals("人工 工智 智能", normText("人工智能"))
    }

    @Test
    fun chineseTwoCharacterQueryUsesFtsPhrase() {
        val query = buildMatchQuery("智能")
        assertEquals("\"智能\"", query.match)
        assertTrue(query.likeTerms.isEmpty())
    }

    @Test
    fun singleChineseCharacterFallsBackToLike() {
        val query = buildMatchQuery("智")
        assertNull(query.match)
        assertEquals(listOf("智"), query.likeTerms)
    }

    @Test
    fun mixedChineseAndLatinQueryUsesAnd() {
        val query = buildMatchQuery("人工智能 AI")
        assertEquals("\"人工 工智 智能\" AND \"ai\"", query.match)
    }

    @Test
    fun htmlAndWidthVariantsAreNormalized() {
        assertEquals("full width", normalizeText("<b>Ｆｕｌｌ</b>   Width"))
    }

    @Test
    fun queryOverTwoHundredCharactersIsRejected() {
        val error = runCatching { buildMatchQuery("a".repeat(201)) }.exceptionOrNull()
        assertTrue(error is SearchQueryTooLongException)
    }

    @Test
    fun snippetCentersAroundFirstMatch() {
        val text = "前".repeat(100) + "智能" + "后".repeat(100)
        val result = snippet(text, "智能", maxChars = 40)
        assertTrue(result.contains("智能"))
        assertTrue(result.length <= 42)
    }

    @Test
    fun refLabelsMatchHostLanguage() {
        assertEquals("transcript · 01:05", refLabel("transcript", "3:65000"))
        assertEquals("Book · 2:5", refLabel("book", "2:5"))
    }
}
