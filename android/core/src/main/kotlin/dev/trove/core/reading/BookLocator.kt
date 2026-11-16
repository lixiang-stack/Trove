package dev.trove.core.reading

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/**
 * Reading position shared with the Host and the Web Shell.
 *
 * Schema 2 keeps the legacy chapter/paragraph/scroll fields so the Web Shell can
 * still restore a position, while Android uses the EPUB fields for Readium.
 */
@Serializable
data class BookLocator(
    @SerialName("chapter_index") val chapterIndex: Int,
    @SerialName("paragraph_index") val paragraphIndex: Int? = null,
    @SerialName("scroll_ratio") val scrollRatio: Double = 0.0,
    @SerialName("epub_href") val epubHref: String? = null,
    @SerialName("epub_progression") val epubProgression: Double? = null,
    @SerialName("epub_total_progression") val epubTotalProgression: Double? = null,
) {
    val isEpub: Boolean get() = !epubHref.isNullOrBlank()

    val fraction: Double
        get() = (epubTotalProgression ?: epubProgression ?: scrollRatio).coerceIn(0.0, 1.0)

    fun toJson(): String {
        if (!isEpub) {
            return json.encodeToString(LegacyBookLocator(chapterIndex, paragraphIndex, scrollRatio))
        }
        return json.encodeToString(
            SchemaTwoBookLocator(
                schema = 2,
                chapterIndex = chapterIndex,
                paragraphIndex = paragraphIndex,
                scrollRatio = scrollRatio,
                epubHref = epubHref.orEmpty(),
                epubProgression = epubProgression,
                epubTotalProgression = epubTotalProgression,
            )
        )
    }

    @Serializable
    private data class LegacyBookLocator(
        @SerialName("chapter_index") val chapterIndex: Int,
        @SerialName("paragraph_index") val paragraphIndex: Int? = null,
        @SerialName("scroll_ratio") val scrollRatio: Double = 0.0,
    )

    @Serializable
    private data class SchemaTwoBookLocator(
        val schema: Int,
        @SerialName("chapter_index") val chapterIndex: Int,
        @SerialName("paragraph_index") val paragraphIndex: Int? = null,
        @SerialName("scroll_ratio") val scrollRatio: Double = 0.0,
        @SerialName("epub_href") val epubHref: String,
        @SerialName("epub_progression") val epubProgression: Double? = null,
        @SerialName("epub_total_progression") val epubTotalProgression: Double? = null,
    )

    companion object {
        private val json = Json { ignoreUnknownKeys = true }
        private val EPUB_FIELDS = setOf(
            "epub_href",
            "epub_progression",
            "epub_total_progression",
        )

        fun parse(raw: String?): BookLocator? {
            if (raw.isNullOrBlank()) return null
            val data = runCatching { json.parseToJsonElement(raw) }.getOrNull()
                as? kotlinx.serialization.json.JsonObject ?: return null
            val schema = data["schema"]?.let {
                runCatching { it.toString().toInt() }.getOrNull()
            }
            if (schema != null && schema != 2) return null
            if (schema == null && data.keys.any { it in EPUB_FIELDS }) return null
            return if (schema == 2) parseSchemaTwo(raw) else parseLegacy(raw)
        }

        private fun parseSchemaTwo(raw: String): BookLocator? {
            val value = runCatching {
                json.decodeFromString<SchemaTwoBookLocator>(raw)
            }.getOrNull() ?: return null
            if (!value.isValid()) return null
            return BookLocator(
                chapterIndex = value.chapterIndex,
                paragraphIndex = value.paragraphIndex,
                scrollRatio = value.scrollRatio,
                epubHref = value.epubHref.takeIf { it.isNotBlank() },
                epubProgression = value.epubProgression,
                epubTotalProgression = value.epubTotalProgression,
            )
        }

        private fun parseLegacy(raw: String): BookLocator? {
            val value = runCatching {
                json.decodeFromString<LegacyBookLocator>(raw)
            }.getOrNull() ?: return null
            if (!value.isValid()) return null
            return BookLocator(
                chapterIndex = value.chapterIndex,
                paragraphIndex = value.paragraphIndex,
                scrollRatio = value.scrollRatio,
            )
        }

        private fun SchemaTwoBookLocator.isValid(): Boolean =
            chapterIndex >= 0 &&
                (paragraphIndex == null || paragraphIndex >= 0) &&
                scrollRatio in 0.0..1.0 &&
                (epubProgression == null || epubProgression in 0.0..1.0) &&
                (epubTotalProgression == null || epubTotalProgression in 0.0..1.0)

        private fun LegacyBookLocator.isValid(): Boolean =
            chapterIndex >= 0 &&
                (paragraphIndex == null || paragraphIndex >= 0) &&
                scrollRatio in 0.0..1.0
    }
}
