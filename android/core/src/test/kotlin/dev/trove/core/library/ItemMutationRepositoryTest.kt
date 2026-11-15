package dev.trove.core.library

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import dev.trove.core.db.ItemEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.network.ProgressRequestDto
import dev.trove.core.network.TagsRequestDto
import dev.trove.core.reading.BookLocator
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
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
class ItemMutationRepositoryTest {
    private lateinit var database: TroveDatabase
    private lateinit var repository: ItemMutationRepository
    private val json = Json { ignoreUnknownKeys = true }

    @Before
    fun setUp() {
        database = TroveDatabase.inMemory(ApplicationProvider.getApplicationContext<Context>())
        repository = ItemMutationRepository(database, now = { 1_790_000_000_000 })
        runBlocking { seed() }
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun tagsAreStoredOptimisticallyAndQueued() = runBlocking {
        val stored = repository.replaceTags("item-1", listOf("#AI，", "记忆"))

        assertEquals(listOf("AI", "记忆"), stored)
        val details = database.itemDao().findDetails("item-1")!!
        assertEquals(setOf("AI", "记忆"), details.tags.map { it.name }.toSet())
        val mutation = database.pendingMutationDao().pending().single()
        assertEquals(ItemMutationRepository.TAGS, mutation.field)
        assertEquals(1_790_000_000_000, mutation.clientUpdatedAt)
        val payload = json.decodeFromString<TagsRequestDto>(mutation.payloadJson)
        assertEquals(listOf("AI", "记忆"), payload.tags)
    }

    @Test
    fun manualConsumptionDoesNotTouchAudioPosition() = runBlocking {
        database.itemDao().applyLocalProgress("item-1", 12.0, "in_progress", 1)

        repository.setConsumption("item-1", "finished")

        val item = database.itemDao().find("item-1")!!
        assertEquals("finished", item.consumptionState)
        assertEquals(12.0, item.audioPositionSec, 0.0)
        val payload = json.decodeFromString<ProgressRequestDto>(
            database.pendingMutationDao().pending().single().payloadJson
        )
        assertEquals("finished", payload.consumptionState)
        assertEquals(null, payload.positionSec)
    }

    @Test
    fun bookProgressUsesSchemaTwoAndAutoFinishesNearTheEnd() = runBlocking {
        repository.saveBookProgress(
            "item-1",
            BookLocator(
                chapterIndex = 2,
                paragraphIndex = 5,
                scrollRatio = 0.96,
                epubHref = "OEBPS/chapter3.xhtml",
                epubProgression = 0.5,
                epubTotalProgression = 0.96,
            ),
        )

        val item = database.itemDao().find("item-1")!!
        assertEquals("finished", item.consumptionState)
        assertTrue(item.bookLocator!!.contains("\"schema\":2"))
        val payload = json.decodeFromString<ProgressRequestDto>(
            database.pendingMutationDao().pending().single().payloadJson
        )
        assertEquals("OEBPS/chapter3.xhtml", payload.bookLocator?.epubHref)
        assertEquals("finished", payload.consumptionState)
    }

    private suspend fun seed() {
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
                hasBook = true,
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
