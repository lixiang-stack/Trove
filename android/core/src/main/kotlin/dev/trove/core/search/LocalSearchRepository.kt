package dev.trove.core.search

import dev.trove.core.db.ItemWithDetails
import dev.trove.core.db.TroveDatabase
import dev.trove.core.library.LibraryItem
import dev.trove.core.library.toLibraryItem
import dev.trove.core.reading.BookRepository
import dev.trove.core.transcript.TranscriptRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

data class SearchFilters(
    val type: String? = null,
    val consumption: String? = null,
    val tag: String? = null,
    val source: String? = null,
)

data class SearchEvidence(
    val docKind: String,
    val ref: String,
    val text: String,
    val snippet: String,
    val label: String,
    val transcriptSeq: Int? = null,
    val chapterIndex: Int? = null,
    val paragraphIndex: Int? = null,
)

data class LocalSearchGroup(
    val item: LibraryItem,
    val evidence: List<SearchEvidence>,
    val score: Double,
)

class LocalSearchRepository(
    private val database: TroveDatabase,
    private val transcriptRepository: TranscriptRepository,
    private val bookRepository: BookRepository,
    private val index: SearchIndex,
) {
    suspend fun isAvailable(): Boolean = index.isAvailable()

    suspend fun indexItem(itemId: String) = withContext(Dispatchers.IO) {
        try {
            val details = database.itemDao().findDetails(itemId)
            if (details == null || !details.isDownloaded()) {
                index.deleteItem(itemId)
                return@withContext
            }
            if (details.item.hasAudio) {
                transcriptRepository.ensureParsed(itemId)
            }
            if (details.item.hasBook) {
                bookRepository.ensureParsed(itemId)
            }
            val documents = buildDocuments(details)
            index.replaceItem(itemId, documents)
        } catch (_: LocalSearchUnavailableException) {
            // Local search is optional; playback and reading keep working.
        }
    }

    suspend fun rebuild() = withContext(Dispatchers.IO) {
        try {
            index.clear()
            for (id in database.itemDao().allIds()) {
                indexItem(id)
            }
        } catch (_: LocalSearchUnavailableException) {
            // Local search is optional; playback and reading keep working.
        }
    }

    suspend fun removeItem(itemId: String) {
        runCatching { index.deleteItem(itemId) }
    }

    suspend fun search(
        query: String,
        filters: SearchFilters = SearchFilters(),
        limit: Int = 50,
    ): List<LocalSearchGroup> = withContext(Dispatchers.IO) {
        val grouped = index.group(index.search(query, limit), limit)
        val results = mutableListOf<LocalSearchGroup>()
        for (group in grouped) {
            val details = database.itemDao().findDetails(group.itemId) ?: continue
            if (!matches(details, filters)) continue
            val item = details.toLibraryItem()
            results += LocalSearchGroup(
                item = item,
                evidence = group.evidence.map {
                    SearchEvidence(
                        docKind = it.docKind,
                        ref = it.ref,
                        text = it.text,
                        snippet = snippet(it.text, query),
                        label = refLabel(it.docKind, it.ref),
                        transcriptSeq = transcriptSeq(it.docKind, it.ref),
                        chapterIndex = bookChapter(it.docKind, it.ref),
                        paragraphIndex = bookParagraph(it.docKind, it.ref),
                    )
                },
                score = group.score,
            )
        }
        results
    }

    private suspend fun buildDocuments(details: ItemWithDetails): List<SearchDocument> {
        val documents = mutableListOf<SearchDocument>()
        val item = details.item
        documents += SearchDocument(item.title, "title", "title")
        item.summary?.takeIf { it.isNotBlank() }?.let {
            documents += SearchDocument(it, "summary", "summary")
        }
        for (tag in details.tags) {
            documents += SearchDocument(tag.name, "tag", tag.name)
        }
        for (segment in database.transcriptSegmentDao().forItem(item.id)) {
            if (segment.text.isBlank()) continue
            documents += SearchDocument(segment.text, "transcript", "${segment.seq}:${segment.startMs}")
        }
        for (paragraph in database.bookDao().paragraphs(item.id)) {
            if (paragraph.text.isBlank()) continue
            documents += SearchDocument(
                paragraph.text,
                "book",
                "${paragraph.chapterIndex}:${paragraph.paragraphIndex}",
            )
        }
        return documents
    }

    private fun matches(details: ItemWithDetails, filters: SearchFilters): Boolean {
        val item = details.item
        if (filters.type != null && item.sourceType != filters.type) return false
        if (filters.consumption != null && item.consumptionState != filters.consumption) return false
        if (filters.source != null && item.platform != filters.source) return false
        if (filters.tag != null) {
            val target = filters.tag.lowercase()
            if (details.tags.none { it.normalizedName == target || it.name.lowercase() == target }) {
                return false
            }
        }
        return true
    }

    private fun ItemWithDetails.isDownloaded(): Boolean =
        artifacts.any { it.downloadState == "completed" }

    private fun transcriptSeq(docKind: String, ref: String): Int? =
        if (docKind == "transcript") ref.substringBefore(':').toIntOrNull() else null

    private fun bookChapter(docKind: String, ref: String): Int? =
        if (docKind == "book") ref.substringBefore(':').toIntOrNull() else null

    private fun bookParagraph(docKind: String, ref: String): Int? =
        if (docKind == "book") ref.substringAfter(':', "").toIntOrNull() else null
}
