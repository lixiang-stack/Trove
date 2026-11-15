package dev.trove.app.search

import dev.trove.core.library.LibraryItem
import dev.trove.core.network.SearchResultDto
import dev.trove.core.search.LocalSearchGroup
import dev.trove.core.search.refLabel

data class SearchUiEvidence(
    val docKind: String,
    val ref: String,
    val label: String,
    val snippet: String,
    val transcriptSeq: Int? = null,
    val chapterIndex: Int? = null,
    val paragraphIndex: Int? = null,
)

data class SearchUiResult(
    val item: LibraryItem,
    val evidence: List<SearchUiEvidence>,
)

fun LocalSearchGroup.toUiResult(): SearchUiResult = SearchUiResult(
    item = item,
    evidence = evidence.map {
        SearchUiEvidence(
            docKind = it.docKind,
            ref = it.ref,
            label = it.label,
            snippet = it.snippet,
            transcriptSeq = it.transcriptSeq,
            chapterIndex = it.chapterIndex,
            paragraphIndex = it.paragraphIndex,
        )
    },
)

fun SearchResultDto.toUiResult(): SearchUiResult = SearchUiResult(
    item = item.toLibraryItem(),
    evidence = evidence.map {
        val transcriptSeq = if (it.docKind == "transcript") {
            it.ref.substringBefore(':').toIntOrNull()
        } else {
            null
        }
        val chapter = if (it.docKind == "book") {
            it.ref.substringBefore(':').toIntOrNull()
        } else {
            null
        }
        val paragraph = if (it.docKind == "book") {
            it.ref.substringAfter(':', "").toIntOrNull()
        } else {
            null
        }
        SearchUiEvidence(
            docKind = it.docKind,
            ref = it.ref,
            label = refLabel(it.docKind, it.ref),
            snippet = it.snippet.ifBlank { it.text },
            transcriptSeq = transcriptSeq,
            chapterIndex = chapter,
            paragraphIndex = paragraph,
        )
    },
)

fun dev.trove.core.network.ItemDto.toLibraryItem(): LibraryItem = LibraryItem(
    id = id,
    version = version,
    sourceType = sourceType,
    platform = platform,
    title = title,
    author = author,
    fetchedAt = fetchedAt ?: 0L,
    language = language,
    durationSec = durationSec,
    summary = summary,
    tags = tags.sortedBy { it.lowercase() },
    processingState = processingState,
    errorCode = errorCode,
    errorMessage = errorMessage,
    consumptionState = consumptionState,
    audioPositionSec = audioPositionSec,
    bookLocator = bookLocator,
    lastConsumedAt = null,
    hasAudio = hasAudio,
    hasBook = hasBook,
    artifacts = emptyList(),
)
