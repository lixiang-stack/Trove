package dev.trove.core.library

import dev.trove.core.db.ItemWithDetails

data class LocalArtifact(
    val kind: String,
    val sha256: String,
    val size: Long,
    val mime: String,
    val version: Int,
    val localPath: String?,
    val downloadState: String,
    val downloadedBytes: Long,
    val errorCode: String?,
)

data class LibraryItem(
    val id: String,
    val version: Int,
    val sourceType: String,
    val platform: String,
    val title: String,
    val author: String?,
    val fetchedAt: Long,
    val language: String?,
    val durationSec: Double?,
    val summary: String?,
    val tags: List<String>,
    val processingState: String,
    val errorCode: String?,
    val errorMessage: String?,
    val consumptionState: String,
    val audioPositionSec: Double,
    val bookLocator: String?,
    val lastConsumedAt: Long?,
    val hasAudio: Boolean,
    val hasBook: Boolean,
    val artifacts: List<LocalArtifact>,
) {
    val audioArtifact: LocalArtifact? get() = artifacts.firstOrNull { it.kind == "audio" }

    val transcriptArtifact: LocalArtifact?
        get() = artifacts.firstOrNull { it.kind == "transcript" }

    val coverArtifact: LocalArtifact? get() = artifacts.firstOrNull { it.kind == "cover" }

    val bookArtifact: LocalArtifact? get() = artifacts.firstOrNull { it.kind == "book" }

    val isInbox: Boolean
        get() = processingState == "failed" ||
            processingState !in setOf("completed", "cancelled")

    val isBookOnly: Boolean get() = hasBook && !hasAudio

    val downloadState: String
        get() = when {
            artifacts.isEmpty() -> "none"
            artifacts.any { it.downloadState == "downloading" } -> "downloading"
            artifacts.any { it.downloadState == "queued" } -> "queued"
            artifacts.any { it.downloadState == "paused" } -> "paused"
            artifacts.any { it.downloadState == "failed" } -> "failed"
            artifacts.all { it.downloadState == "completed" } -> "completed"
            artifacts.any { it.downloadState == "completed" } -> "partial"
            else -> "none"
        }

    val downloadProgress: Float
        get() {
            val total = artifacts.sumOf { it.size }
            if (total <= 0) return 0f
            return (artifacts.sumOf { it.downloadedBytes }.toFloat() / total).coerceIn(0f, 1f)
        }
}

fun ItemWithDetails.toLibraryItem(): LibraryItem = LibraryItem(
    id = item.id,
    version = item.version,
    sourceType = item.sourceType,
    platform = item.platform,
    title = item.title,
    author = item.author,
    fetchedAt = item.fetchedAt,
    language = item.language,
    durationSec = item.durationSec,
    summary = item.summary,
    tags = tags.map { it.name }.sortedBy { it.lowercase() },
    processingState = item.processingState,
    errorCode = item.errorCode,
    errorMessage = item.errorMessage,
    consumptionState = item.consumptionState,
    audioPositionSec = item.audioPositionSec,
    bookLocator = item.bookLocator,
    lastConsumedAt = item.lastConsumedAt,
    hasAudio = item.hasAudio,
    hasBook = item.hasBook,
    artifacts = artifacts.sortedBy { it.kind }.map {
        LocalArtifact(
            kind = it.kind,
            sha256 = it.sha256,
            size = it.size,
            mime = it.mime,
            version = it.version,
            localPath = it.localPath,
            downloadState = it.downloadState,
            downloadedBytes = it.downloadedBytes,
            errorCode = it.errorCode,
        )
    },
)
