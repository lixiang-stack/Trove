package dev.trove.core.tags

import java.text.Normalizer

private const val TAG_MAX_LENGTH = 64
private val WHITESPACE = Regex("\\s+")
private val HASH_PREFIX = Regex("^[#＃]+")
private val TRAILING_PUNCTUATION = Regex("[.,;:!?，。；：！？]+$")

private val IRREGULAR_PLURALS = mapOf(
    "people" to "person",
    "children" to "child",
    "men" to "man",
    "women" to "woman",
    "teeth" to "tooth",
    "feet" to "foot",
    "mice" to "mouse",
    "geese" to "goose",
)

data class NormalizedTag(val name: String, val normalizedName: String)

class InvalidTagException(val code: String, message: String) : IllegalArgumentException(message)

/**
 * Mirrors the Host's tag normalization so optimistic offline edits converge once
 * the canonical Tag list arrives.
 */
fun normalizeTag(raw: String): NormalizedTag {
    var display = Normalizer.normalize(raw, Normalizer.Form.NFKC).trim()
    display = HASH_PREFIX.replace(display, "").trim()
    display = WHITESPACE.replace(display, " ")
    display = TRAILING_PUNCTUATION.replace(display, "")
    if (display.isEmpty()) {
        throw InvalidTagException("tag.empty", "Tag cannot be empty")
    }
    if (display.length > TAG_MAX_LENGTH) {
        throw InvalidTagException("tag.too_long", "Tag cannot exceed $TAG_MAX_LENGTH characters")
    }
    var normalized = Normalizer.normalize(display, Normalizer.Form.NFKC).lowercase()
    normalized = WHITESPACE.replace(normalized, " ").trim()
    if (normalized.all { it.code < 128 } && normalized.all { it.isLetter() }) {
        normalized = naiveSingular(normalized)
    }
    return NormalizedTag(display, normalized)
}

fun normalizeTags(rawTags: List<String>): List<NormalizedTag> {
    val seen = mutableSetOf<String>()
    val result = mutableListOf<NormalizedTag>()
    for (raw in rawTags) {
        val tag = normalizeTag(raw)
        if (seen.add(tag.normalizedName)) {
            result += tag
        }
    }
    return result
}

private fun naiveSingular(value: String): String {
    IRREGULAR_PLURALS[value]?.let { return it }
    if (value.length > 3 && value.endsWith("ies")) return value.dropLast(3) + "y"
    if (value.length > 3 && value.endsWith("ses")) return value.dropLast(2)
    if (value.length > 3 && value.endsWith("xes")) return value.dropLast(2)
    if (value.length > 3 && value.endsWith("zes")) return value.dropLast(2)
    if (value.length > 3 && value.endsWith("ches")) return value.dropLast(2)
    if (value.length > 3 && value.endsWith("shes")) return value.dropLast(2)
    if (value.length > 3 && value.endsWith("s") && !value.endsWith("ss")) {
        return value.dropLast(1)
    }
    return value
}
