package dev.trove.app.ui.components

import dev.trove.core.library.LibraryItem
import java.text.BreakIterator
import java.text.Normalizer
import java.util.Locale

private val WHITESPACE = Regex("\\s+")
private val LEADING_YEAR = Regex("^(?:19|20)\\d{2}\\s*[年.\\-/]?\\s*")
private val LEADING_BRACKET = Regex("^\\s*[\\[【(（][^\\]】)）]{1,16}[\\]】)）]\\s*")
private val QUALITY_TAG = Regex(
    "(?i)(?:^|[\\s\\-_|·:：])(?:4k|8k|1080p|720p|hd|hdr|高清版?|超清版?|蓝光版?|完整版|官方|中字|字幕|全集|全\\d+[讲集期])(?=$|[\\s\\-_|·:：])"
)
private val EPISODE_MARKER = Regex(
    "(?i)(?:第\\s*\\d+\\s*[集讲期话]|\\bep?\\s*\\d{1,4}\\b|\\bp\\s*\\d{1,4}\\b|\\bs\\d{1,2}\\s*e\\s*\\d{1,3}\\b)"
)
private val BRACKETED_TITLE = Regex("^《(.+)》$")
private val WORD_SEPARATOR = Regex("[^\\p{L}\\p{N}]+")
private const val LATIN_FULL_TITLE_MAX_LENGTH = 24
private const val CJK_FULL_TITLE_MAX_LENGTH = 8
private val TRIM_CHARS = charArrayOf(
    ' ', '-', '_', '|', '·', ':', '：', '，', ',', '。', '.', '、',
    '《', '》', '「', '」', '"', '\'',
)
private val STOP_WORDS = setOf(
    "a", "an", "the", "of", "for", "to", "in", "on", "with", "and", "or",
)

internal fun coverLabel(item: LibraryItem): String =
    coverText(item.title, item.collectionTitle)

internal fun coverSeed(item: LibraryItem): String =
    item.collectionId?.takeIf { it.isNotBlank() } ?: item.id

internal fun coverText(
    title: String,
    collectionTitle: String? = null,
    allowFullTitle: Boolean = true,
): String {
    val cleaned = cleanTitle(title, collectionTitle)
    if (cleaned.text.isBlank()) return ""
    if (allowFullTitle && cleaned.hasExplicitTitle) return cleaned.text
    return labelFor(cleaned.text, allowFullTitle)
}

private data class CleanedTitle(val text: String, val hasExplicitTitle: Boolean)

private fun cleanTitle(title: String, collectionTitle: String?): CleanedTitle {
    val normalized = normalize(title)
    var text = normalized
    var hasCleanTitle = false
    BRACKETED_TITLE.matchEntire(normalized)?.let {
        text = it.groupValues[1].trim(*TRIM_CHARS)
        hasCleanTitle = true
    }

    val collection = collectionTitle?.let(::normalize).orEmpty()
    if (collection.isNotBlank() && text.startsWith(collection)) {
        text = text.removePrefix(collection)
    }
    text = LEADING_BRACKET.replace(text, "")
    text = LEADING_YEAR.replace(text, " ")
    text = QUALITY_TAG.replace(text, " ")

    var hasExplicitSubtitle = false
    val marker = EPISODE_MARKER.findAll(text).lastOrNull()
    if (marker != null && marker.range.last + 1 < text.length) {
        val subtitle = text.substring(marker.range.last + 1).trim(*TRIM_CHARS)
        if (subtitle.isNotBlank()) {
            text = subtitle
            hasExplicitSubtitle = true
        }
    }
    return CleanedTitle(
        text = text.trim(*TRIM_CHARS),
        hasExplicitTitle = hasCleanTitle || hasExplicitSubtitle,
    )
}

private fun labelFor(text: String, allowFullTitle: Boolean): String {
    val content = text.filter { it.isCjk() || it.isLetterOrDigit() }
    val first = text.firstOrNull { it.isCjk() || it.isLetterOrDigit() } ?: return ""
    val onlyCjkContent = text.none { it.isLetterOrDigit() && !it.isCjk() }
    return when {
        first.isCjk() -> {
            if (allowFullTitle && onlyCjkContent && content.length <= CJK_FULL_TITLE_MAX_LENGTH) {
                content
            } else {
                takeGraphemes(content, 2)
            }
        }
        first.isLetter() -> {
            if (allowFullTitle &&
                text.none { it.isCjk() } &&
                text.length <= LATIN_FULL_TITLE_MAX_LENGTH
            ) {
                text
            } else {
                latinInitials(text)
            }
        }
        else -> takeGraphemes(content, 2)
    }
}

private fun normalize(value: String): String =
    Normalizer.normalize(value, Normalizer.Form.NFKC)
        .replace(WHITESPACE, " ")
        .trim()

private fun latinInitials(text: String): String {
    val words = text.split(WORD_SEPARATOR)
        .map { it.trim() }
        .filter { word -> word.any { it.isLetterOrDigit() } }
    val latinWords = words.filter { word -> word.firstOrNull()?.isLatinLetter() == true }
    val significant = latinWords.filter { it.lowercase(Locale.ROOT) !in STOP_WORDS }
    val picked = if (significant.size >= 2) significant.take(2) else latinWords.take(2)
    if (picked.size < 2) return takeGraphemes(text, 2).uppercase(Locale.ROOT)
    return picked.mapNotNull { it.firstOrNull { char -> char.isLetterOrDigit() } }
        .joinToString("")
        .uppercase(Locale.ROOT)
}

private fun takeGraphemes(text: String, count: Int): String {
    if (text.isEmpty()) return ""
    val iterator = BreakIterator.getCharacterInstance(Locale.ROOT)
    iterator.setText(text)
    var end = iterator.first()
    repeat(count) {
        val next = iterator.next()
        if (next == BreakIterator.DONE) return text
        end = next
    }
    return text.substring(0, end)
}

private fun Char.isCjk(): Boolean =
    this in '\u3400'..'\u4DBF' ||
        this in '\u4E00'..'\u9FFF' ||
        this in '\uF900'..'\uFAFF' ||
        this in '\u3040'..'\u30FF' ||
        this in '\uAC00'..'\uD7AF'

private fun Char.isLatinLetter(): Boolean =
    this in 'A'..'Z' || this in 'a'..'z'
