package dev.trove.core.db

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Device-only smoke for the production bundled SQLite driver.
 *
 * Robolectric tests use framework SQLite, which does not exercise the
 * SupportSQLiteOpenHelper-free Room path. This catches startup failures such as
 * "Cannot return a SupportSQLiteOpenHelper since no ... Factory was configured".
 */
@RunWith(AndroidJUnit4::class)
class TroveDatabaseDeviceTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private lateinit var database: TroveDatabase

    @Before
    fun setUp() {
        context.deleteDatabase(TroveDatabase.NAME)
        database = TroveDatabase.create(context)
    }

    @After
    fun tearDown() {
        database.close()
        context.deleteDatabase(TroveDatabase.NAME)
    }

    @Test
    fun productionBundledDriverTransactionsWork() = runBlocking {
        database.writeTransaction {
            database.itemDao().upsert(
                ItemEntity(
                    id = "device-item",
                    version = 1,
                    sourceType = "local_audio",
                    platform = "local",
                    title = "Device transaction",
                    author = null,
                    publishedAt = null,
                    fetchedAt = 1,
                    language = "zh",
                    durationSec = 10.0,
                    summary = null,
                    processingState = "completed",
                    errorCode = null,
                    errorMessage = null,
                    hasAudio = true,
                    hasBook = false,
                    consumptionState = "in_progress",
                    audioPositionSec = 3.0,
                    bookLocator = null,
                    lastConsumedAt = 1,
                    contentSeq = 1,
                    stateSeq = 1,
                    lastSyncedAt = 1,
                )
            )
            database.artifactDao().upsert(
                ArtifactEntity(
                    itemId = "device-item",
                    kind = "audio",
                    sha256 = "a".repeat(64),
                    size = 10,
                    mime = "audio/mp4",
                    version = 1,
                    localPath = null,
                    downloadState = "none",
                )
            )
        }

        assertEquals(1, database.itemDao().count())
        assertEquals(1, database.artifactDao().forItem("device-item").size)
    }
}
