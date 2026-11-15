package dev.trove.app.playback

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import dev.trove.core.db.ItemEntity
import dev.trove.core.db.TroveDatabase
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class PlaybackProgressRecorderTest {
    private lateinit var database: TroveDatabase
    private var now = 1_790_000_000_000L

    @Before
    fun setUp() {
        database = TroveDatabase.inMemory(ApplicationProvider.getApplicationContext<Context>())
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun savesProgressLocallyAndQueuesOneCoalescedMutation() = runBlocking {
        seedItem()
        val recorder = PlaybackProgressRecorder(database) { now }

        recorder.savePosition("item-1", 10_000, ended = false)
        now += 5_000
        recorder.savePosition("item-1", 15_000, ended = false)

        val item = database.itemDao().find("item-1")!!
        assertEquals(15.0, item.audioPositionSec, 0.0)
        assertEquals("in_progress", item.consumptionState)
        assertEquals(now, item.lastConsumedAt)
        assertEquals(1, database.pendingMutationDao().count())
        val mutation = database.pendingMutationDao().pending().single()
        assertEquals("audio_progress", mutation.field)
        assertEquals(now, mutation.clientUpdatedAt)
        assert(mutation.payloadJson.contains("\"position_sec\":15.0"))
    }

    @Test
    fun endedMarksFinishedAndUsesFullDuration() = runBlocking {
        seedItem()
        val recorder = PlaybackProgressRecorder(database) { now }

        recorder.savePosition("item-1", 99_000, ended = true)

        val item = database.itemDao().find("item-1")!!
        assertEquals(100.0, item.audioPositionSec, 0.0)
        assertEquals("finished", item.consumptionState)
    }

    @Test
    fun repeatedSamePositionDoesNotQueueAnotherMutation() = runBlocking {
        seedItem()
        val recorder = PlaybackProgressRecorder(database) { now }
        recorder.savePosition("item-1", 10_000, ended = false)
        val firstKey = database.pendingMutationDao().pending().single().idempotencyKey

        recorder.savePosition("item-1", 10_100, ended = false)

        val mutations = database.pendingMutationDao().pending()
        assertEquals(1, mutations.size)
        assertEquals(firstKey, mutations.single().idempotencyKey)
    }

    @Test
    fun progressForMissingItemIsIgnored() = runBlocking {
        val recorder = PlaybackProgressRecorder(database) { now }
        recorder.savePosition("missing", 10_000, ended = false)
        assertEquals(0, database.pendingMutationDao().count())
    }

    private suspend fun seedItem() {
        database.itemDao().upsert(
            ItemEntity(
                id = "item-1",
                version = 1,
                sourceType = "video_url",
                platform = "youtube",
                title = "Item",
                author = null,
                publishedAt = null,
                fetchedAt = 1,
                language = "zh",
                durationSec = 100.0,
                summary = null,
                processingState = "completed",
                errorCode = null,
                errorMessage = null,
                hasAudio = true,
                hasBook = false,
                consumptionState = "unstarted",
                audioPositionSec = 0.0,
                bookLocator = null,
                lastConsumedAt = null,
                contentSeq = 1,
                stateSeq = 1,
                lastSyncedAt = 1,
            )
        )
    }
}
