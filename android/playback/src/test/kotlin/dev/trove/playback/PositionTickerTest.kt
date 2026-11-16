package dev.trove.playback

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class PositionTickerTest {
    @Test
    fun stopThenStartResumesTicks() = runTest {
        var ticks = 0
        val ticker = PositionTicker(
            scope = this,
            intervalMs = 1_000,
            tick = { ticks += 1 },
        )

        ticker.start()
        runCurrent()
        assertEquals(1, ticks)
        advanceTimeBy(2_000)
        runCurrent()
        assertEquals(3, ticks)

        ticker.stop()
        advanceTimeBy(3_000)
        runCurrent()
        assertEquals(3, ticks)

        ticker.start()
        runCurrent()
        assertEquals(4, ticks)
        advanceTimeBy(1_000)
        runCurrent()
        assertEquals(5, ticks)
        ticker.stop()
    }
}
