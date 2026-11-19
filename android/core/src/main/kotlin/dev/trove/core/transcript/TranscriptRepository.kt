package dev.trove.core.transcript

import dev.trove.core.db.TranscriptSegmentEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.db.writeTransaction
import dev.trove.core.storage.ArtifactFileStore
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

sealed interface TranscriptLoadResult {
    data class Ready(val segmentCount: Int) : TranscriptLoadResult

    data object NotDownloaded : TranscriptLoadResult

    data object Empty : TranscriptLoadResult

    data object Failed : TranscriptLoadResult
}

class TranscriptRepository(
    private val database: TroveDatabase,
    private val fileStore: ArtifactFileStore,
    private val remoteSegments: suspend (String) -> List<TranscriptSegment>? = { null },
) {
    fun observe(itemId: String): Flow<List<TranscriptSegment>> =
        database.transcriptSegmentDao().observeForItem(itemId).map { rows ->
            rows.map {
                TranscriptSegment(
                    seq = it.seq,
                    startMs = it.startMs,
                    endMs = it.endMs,
                    text = it.text,
                )
            }
        }

    suspend fun ensureParsed(itemId: String): TranscriptLoadResult {
        val cached = database.transcriptSegmentDao().countForItem(itemId)
        if (cached > 0) return TranscriptLoadResult.Ready(cached)
        val artifact = database.artifactDao().find(itemId, "transcript")
        if (artifact != null && artifact.downloadState == "completed") {
            val file = fileStore.existingFile(itemId, "transcript", artifact.localPath)
            if (file != null) return parseFile(itemId, file)
        }
        return loadRemote(itemId)
    }

    private suspend fun loadRemote(itemId: String): TranscriptLoadResult {
        val segments = try {
            remoteSegments(itemId)
        } catch (error: CancellationException) {
            throw error
        } catch (_: Exception) {
            null
        } ?: return TranscriptLoadResult.NotDownloaded
        database.writeTransaction {
            database.transcriptSegmentDao().deleteForItem(itemId)
            if (segments.isNotEmpty()) {
                database.transcriptSegmentDao().insertAll(
                    segments.map {
                        TranscriptSegmentEntity(
                            itemId = itemId,
                            seq = it.seq,
                            startMs = it.startMs,
                            endMs = it.endMs,
                            text = it.text,
                        )
                    }
                )
            }
        }
        return if (segments.isEmpty()) {
            TranscriptLoadResult.Empty
        } else {
            TranscriptLoadResult.Ready(segments.size)
        }
    }

    suspend fun parseFile(itemId: String, file: File): TranscriptLoadResult {
        val segments = try {
            TranscriptParser.parse(file.readText())
        } catch (_: TranscriptParseException) {
            return TranscriptLoadResult.Failed
        } catch (_: java.io.IOException) {
            return TranscriptLoadResult.Failed
        }
        database.writeTransaction {
            database.transcriptSegmentDao().deleteForItem(itemId)
            if (segments.isNotEmpty()) {
                database.transcriptSegmentDao().insertAll(
                    segments.map {
                        TranscriptSegmentEntity(
                            itemId = itemId,
                            seq = it.seq,
                            startMs = it.startMs,
                            endMs = it.endMs,
                            text = it.text,
                        )
                    }
                )
            }
        }
        return if (segments.isEmpty()) {
            TranscriptLoadResult.Empty
        } else {
            TranscriptLoadResult.Ready(segments.size)
        }
    }
}

fun queryMatches(text: String, query: String): Boolean =
    query.isBlank() || text.contains(query, ignoreCase = true)

fun highlightRanges(text: String, query: String): List<IntRange> {
    if (query.isBlank()) return emptyList()
    val ranges = mutableListOf<IntRange>()
    var start = 0
    while (start <= text.length - query.length) {
        val index = text.indexOf(query, start, ignoreCase = true)
        if (index < 0) break
        ranges += index until index + query.length
        start = index + query.length
    }
    return ranges
}
