package dev.trove.core.transcript

data class TranscriptSegment(
    val seq: Int,
    val startMs: Long,
    val endMs: Long,
    val text: String,
)
