package dev.trove.core.db

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class TroveDatabaseTest {
    private lateinit var database: TroveDatabase

    @Before
    fun setUp() {
        database = TroveDatabase.inMemory(ApplicationProvider.getApplicationContext<Context>())
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun emptyDatabaseCreatesAllTablesAndIndexes() {
        val tables = mutableSetOf<String>()
        val indexes = mutableSetOf<String>()
        database.openHelper.readableDatabase.query(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'index')"
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val type = cursor.getString(1)
                if (type == "table") tables += cursor.getString(0)
                if (type == "index") indexes += cursor.getString(0)
            }
        }
        assertTrue(
            tables.containsAll(
                setOf(
                    "items",
                    "artifacts",
                    "transcript_segments",
                    "book_chapters",
                    "book_paragraphs",
                    "tags",
                    "item_tags",
                    "sync_cursor",
                    "pending_mutations",
                )
            )
        )
        assertTrue(indexes.any { it.startsWith("index_artifacts_item_id") })
        assertTrue(indexes.any { it.startsWith("index_item_tags_tag_name") })
    }

    @Test
    fun itemRoundTripsThroughDao() = runBlocking {
        val item = ItemEntity(
            id = "item-1",
            version = 3,
            sourceType = "video_url",
            platform = "youtube",
            title = "Round trip",
            author = null,
            publishedAt = null,
            fetchedAt = 1_790_000_000_000,
            language = "zh",
            durationSec = 12.5,
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
            contentSeq = 3,
            stateSeq = 4,
            lastSyncedAt = 1_790_000_000_100,
        )
        database.itemDao().upsert(item)
        assertEquals(1, database.itemDao().count())
        assertEquals(item, database.itemDao().find("item-1"))
    }
}
