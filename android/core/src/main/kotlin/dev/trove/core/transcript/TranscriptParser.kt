package dev.trove.core.transcript

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

class TranscriptParseException(message: String, cause: Throwable? = null) :
    Exception(message, cause)

object TranscriptParser {
    private val json = Json { ignoreUnknownKeys = true }

    fun parse(text: String): List<TranscriptSegment> {
        val document = try {
            json.decodeFromString<TranscriptDocumentDto>(text)
        } catch (error: Exception) {
            throw TranscriptParseException("Invalid transcript JSON", error)
        }
        val seen = mutableSetOf<Int>()
        return document.segments.map { segment ->
            if (segment.seq < 0) {
                throw TranscriptParseException("Transcript segment seq must be non-negative")
            }
            if (!seen.add(segment.seq)) {
                throw TranscriptParseException("Duplicate transcript segment seq ${segment.seq}")
            }
            if (segment.startMs < 0 || segment.endMs < segment.startMs) {
                throw TranscriptParseException("Invalid timestamp range for seq ${segment.seq}")
            }
            TranscriptSegment(
                seq = segment.seq,
                startMs = segment.startMs,
                endMs = segment.endMs,
                text = segment.text,
            )
        }.sortedBy { it.seq }
    }

    fun timestamp(milliseconds: Long): String {
        val seconds = (milliseconds.coerceAtLeast(0) / 1000).toInt()
        val minutes = seconds / 60
        val remainder = seconds % 60
        val hours = minutes / 60
        return if (hours > 0) {
            "$hours:${(minutes % 60).toString().padStart(2, '0')}:${remainder.toString().padStart(2, '0')}"
        } else {
            "$minutes:${remainder.toString().padStart(2, '0')}"
        }
    }
}

@Serializable
private data class TranscriptDocumentDto(
    val language: String? = null,
    val model: String? = null,
    val segments: List<TranscriptSegmentDto>,
)

@Serializable
private data class TranscriptSegmentDto(
    val seq: Int,
    @SerialName("start_ms") val startMs: Long,
    @SerialName("end_ms") val endMs: Long,
    val text: String,
)
