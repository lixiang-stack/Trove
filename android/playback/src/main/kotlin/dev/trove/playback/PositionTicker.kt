package dev.trove.playback

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Repeating tick that can be stopped and restarted. Keeping the job nullable
 * matters: a cancelled job must not block a later start.
 */
internal class PositionTicker(
    private val scope: CoroutineScope,
    private val intervalMs: Long,
    private val tick: () -> Unit,
) {
    private var job: Job? = null

    fun start() {
        if (job != null) return
        job = scope.launch {
            while (isActive) {
                tick()
                delay(intervalMs)
            }
        }
    }

    fun stop() {
        job?.cancel()
        job = null
    }
}
