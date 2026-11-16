package dev.trove.core.search

import java.text.Normalizer

const val MAX_QUERY_LENGTH = 200

class SearchQueryTooLongException(
    message: String = "Query is too long; maximum $MAX_QUERY_LENGTH characters",
) : IllegalArgumentException(message)

data class MatchQuery(
    val match: String?,
    val likeTerms: List<String>,
)

private data class ScannedToken(val isCjk: Boolean, val value: String)

private val HTML_TAGS = Regex("<[^>]+>")
private val WHITESPACE = Regex("\\s+")
private val LATIN = Regex("[0-9a-z]+(?:[._+-][0-9a-z]+)*")

private val CJK_RANGES = listOf(
    0x3400..0x4DBF,
    0x4E00..0x9FFF,
    0xF900..0xFAFF,
    0x3040..0x30FF,
    0xAC00..0xD7AF,
)

fun isCjk(char: Char): Boolean = CJK_RANGES.any { char.code in it }

fun normalizeText(value: String): String {
    var text = Normalizer.normalize(value, Normalizer.Form.NFKC)
    text = HTML_TAGS.replace(text, " ")
    text = text.lowercase()
    return WHITESPACE.replace(text, " ").trim()
}

private fun scan(normalized: String): Sequence<ScannedToken> = sequence {
    var position = 0
    while (position < normalized.length) {
        val char = normalized[position]
        if (isCjk(char)) {
            val start = position
            while (position < normalized.length && isCjk(normalized[position])) {
                position += 1
            }
            yield(ScannedToken(true, normalized.substring(start, position)))
            continue
        }
        val latin = LATIN.find(normalized, position)
        if (latin != null && latin.range.first == position) {
            yield(ScannedToken(false, latin.value))
            position = latin.range.last + 1
            continue
        }
        position += 1
    }
}

fun documentTokens(value: String): List<String> {
    val tokens = mutableListOf<String>()
    for (token in scan(normalizeText(value))) {
        if (token.isCjk && token.value.length > 1) {
            for (index in 0 until token.value.length - 1) {
                tokens += token.value.substring(index, index + 2)
            }
        } else {
            tokens += token.value
        }
    }
    return tokens
}

fun normText(value: String): String = documentTokens(value).joinToString(" ")

fun queryTokens(query: String): List<String> = documentTokens(query)

fun buildMatchQuery(query: String): MatchQuery {
    val normalized = normalizeText(query)
    if (normalized.length > MAX_QUERY_LENGTH) {
        throw SearchQueryTooLongException()
    }
    val phrases = mutableListOf<String>()
    val likeTerms = mutableListOf<String>()
    for (token in scan(normalized)) {
        if (!token.isCjk) {
            phrases += "\"${token.value}\""
        } else if (token.value.length == 1) {
            likeTerms += token.value
        } else {
            val bigrams = (0 until token.value.length - 1)
                .map { token.value.substring(it, it + 2) }
            phrases += "\"${bigrams.joinToString(" ")}\""
        }
    }
    return MatchQuery(
        match = phrases.takeIf { it.isNotEmpty() }?.joinToString(" AND "),
        likeTerms = likeTerms,
    )
}

fun queryWords(query: String): List<String> =
    scan(normalizeText(query)).map { it.value }.toList()

fun snippet(text: String, query: String, maxChars: Int = 180): String {
    if (text.length <= maxChars) return text
    val folded = text.lowercase()
    val positions = queryWords(query).map { folded.indexOf(it) }.filter { it >= 0 }
    if (positions.isEmpty()) {
        return text.take(maxChars).trimEnd() + "…"
    }
    val index = positions.min()
    var start = maxOf(0, index - maxChars / 3)
    val end = minOf(text.length, start + maxChars)
    start = maxOf(0, end - maxChars)
    val prefix = if (start > 0) "…" else ""
    val suffix = if (end < text.length) "…" else ""
    return prefix + text.substring(start, end).trim() + suffix
}

fun refLabel(docKind: String, ref: String): String = when (docKind) {
    "transcript" -> {
        val seconds = ref.substringAfter(':', "").toLongOrNull()?.div(1000)
        if (seconds != null) {
            "transcript · %02d:%02d".format(seconds / 60, seconds % 60)
        } else {
            "transcript"
        }
    }

    "book" -> "Book · $ref"
    "title" -> "Title"
    "summary" -> "Summary"
    "tag" -> "Tag"
    else -> docKind
}
