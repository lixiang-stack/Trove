package dev.trove.core.transcript

data class TranscriptSegment(
    val seq: Int,
    val startMs: Long,
    val endMs: Long,
    val text: String,
)

fun List<TranscriptSegment>.activeAt(positionMs: Long): TranscriptSegment? {
    if (isEmpty()) return null
    return lastOrNull { it.startMs <= positionMs } ?: first()
}
