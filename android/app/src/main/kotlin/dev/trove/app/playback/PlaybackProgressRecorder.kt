package dev.trove.app.playback

import dev.trove.core.db.PendingMutationEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.db.writeTransaction
import dev.trove.core.network.ProgressRequestDto
import dev.trove.playback.PlaybackProgressSink
import java.util.UUID
import kotlinx.serialization.json.Json

private const val AUTO_START_MAX_SECONDS = 5.0
private const val AUTO_FINISH_RATIO = 0.95

class PlaybackProgressRecorder(
    private val database: TroveDatabase,
    private val now: () -> Long = System::currentTimeMillis,
) : PlaybackProgressSink {
    private val json = Json { encodeDefaults = true }

    override suspend fun savePosition(itemId: String, positionMs: Long, ended: Boolean) {
        database.writeTransaction {
            val item = database.itemDao().find(itemId) ?: return@writeTransaction
            val duration = item.durationSec
            val position = when {
                ended && duration != null && duration > 0 -> duration
                else -> positionMs / 1000.0
            }
            val state = deriveState(item.consumptionState, position, duration, ended)
            if (!ended && state == item.consumptionState &&
                kotlin.math.abs(item.audioPositionSec - position) < MIN_PROGRESS_DELTA_SECONDS
            ) {
                return@writeTransaction
            }
            val timestamp = now()
            database.itemDao().applyLocalProgress(
                id = itemId,
                positionSec = position,
                consumptionState = state,
                lastConsumedAt = timestamp,
            )
            val payload = json.encodeToString(
                ProgressRequestDto(
                    positionSec = position,
                    consumptionState = state,
                    clientUpdatedAt = timestamp,
                )
            )
            database.pendingMutationDao().deleteForField(itemId, AUDIO_PROGRESS)
            database.pendingMutationDao().upsert(
                PendingMutationEntity(
                    idempotencyKey = UUID.randomUUID().toString(),
                    itemId = itemId,
                    field = AUDIO_PROGRESS,
                    payloadJson = payload,
                    clientUpdatedAt = timestamp,
                    createdAt = timestamp,
                )
            )
        }
    }

    private fun deriveState(
        current: String,
        position: Double,
        duration: Double?,
        ended: Boolean,
    ): String {
        if (ended) return FINISHED
        if (duration != null && duration > 0) {
            if (position >= duration * AUTO_FINISH_RATIO) return FINISHED
            if (position >= minOf(AUTO_START_MAX_SECONDS, maxOf(duration * 0.02, 1.0))) {
                return IN_PROGRESS
            }
            return current
        }
        return if (position > 0) IN_PROGRESS else current
    }

    private companion object {
        const val AUDIO_PROGRESS = "audio_progress"
        const val IN_PROGRESS = "in_progress"
        const val FINISHED = "finished"
        const val MIN_PROGRESS_DELTA_SECONDS = 0.5
    }
}
