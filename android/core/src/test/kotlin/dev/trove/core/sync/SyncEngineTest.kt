package dev.trove.core.sync

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import dev.trove.core.db.ArtifactEntity
import dev.trove.core.db.PendingMutationEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.network.DeviceListResponse
import dev.trove.core.network.DeviceTokenRequest
import dev.trove.core.network.DeviceTokenResponse
import dev.trove.core.network.FeedPreviewRequestDto
import dev.trove.core.network.FeedPreviewResponseDto
import dev.trove.core.network.HealthDto
import dev.trove.core.network.ItemCreateRequestDto
import dev.trove.core.network.ItemCreateResponseDto
import dev.trove.core.network.ItemDto
import dev.trove.core.network.ManifestDto
import dev.trove.core.network.MutationItemDto
import dev.trove.core.network.MutationResponseDto
import dev.trove.core.network.ProgressRequestDto
import dev.trove.core.network.SearchResponseDto
import dev.trove.core.network.SyncFileDto
import dev.trove.core.network.SyncItemDto
import dev.trove.core.network.SyncStateDto
import dev.trove.core.network.SyncStateItemDto
import dev.trove.core.network.TagsRequestDto
import dev.trove.core.network.TombstoneDto
import dev.trove.core.network.TroveApi
import dev.trove.core.network.TroveApiException
import dev.trove.core.network.TroveClient
import dev.trove.core.network.TroveNetworkException
import dev.trove.core.storage.ArtifactFileStore
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import retrofit2.Response

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class SyncEngineTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    private lateinit var database: TroveDatabase
    private lateinit var fileStore: ArtifactFileStore
    private lateinit var api: QueueApi

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        database = TroveDatabase.inMemory(context)
        fileStore = ArtifactFileStore(temporaryFolder.newFolder("artifacts"))
        api = QueueApi()
    }

    @After
    fun tearDown() {
        database.close()
    }

    private fun engine(
        nowPlaying: () -> String? = { null },
        downloadQueue: DownloadQueue? = null,
    ) = SyncEngine(
        database = database,
        clientProvider = { TroveClient(api) },
        fileStore = fileStore,
        downloadQueue = downloadQueue,
        pageSize = 2,
        now = { 1_790_000_000_000 },
        nowPlayingItemId = nowPlaying,
    )

    @Test
    fun firstSyncAppliesPagedManifestAndState() = runBlocking {
        api.manifestPages += manifest(
            items = listOf(item("a", version = 1)), cursor = "2", hasMore = true,
        )
        api.manifestPages += manifest(
            items = listOf(item("b", version = 1)), cursor = "4", hasMore = false,
        )
        api.statePages += SyncStateDto(
            items = listOf(
                SyncStateItemDto(
                    id = "a",
                    stateSeq = 7,
                    audioPositionSec = 42.5,
                    consumptionState = "in_progress",
                    lastConsumedAt = 123,
                )
            ),
            nextCursor = "7",
            hasMore = false,
            epoch = EPOCH,
        )

        val result = engine().sync()

        assertTrue(result.success)
        val items = database.itemDao().observeAll().first()
        assertEquals(listOf("a", "b"), items.map { it.id }.sorted())
        val a = database.itemDao().findDetails("a")!!
        assertEquals(setOf("AI", "记忆"), a.tags.map { it.name }.toSet())
        assertEquals(42.5, a.item.audioPositionSec, 0.0)
        assertEquals(7, a.item.stateSeq)
        assertEquals("4", database.syncCursorDao().current()?.contentCursor)
        assertEquals(listOf(null, "2"), api.requestedCursors.take(2))
        assertEquals(1_790_000_000_000, database.syncCursorDao().current()?.lastSuccessAt)
    }

    @Test
    fun incrementalSyncAppliesOnlyChangedItemsAndKeepsLocalState() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.statePages += SyncStateDto(
            items = listOf(
                SyncStateItemDto(
                    id = "a",
                    stateSeq = 3,
                    audioPositionSec = 12.0,
                    consumptionState = "in_progress",
                    lastConsumedAt = 10,
                )
            ),
            nextCursor = "3",
            hasMore = false,
            epoch = EPOCH,
        )
        engine().sync()

        api.manifestPages.clear()
        api.statePages.clear()
        api.manifestPages += manifest(
            items = listOf(item("a", version = 2, title = "Updated")),
            cursor = "2",
        )
        api.statePages += SyncStateDto(
            items = emptyList(),
            nextCursor = "3",
            hasMore = false,
            epoch = EPOCH,
        )
        val result = engine().sync()

        assertTrue(result.success)
        val a = database.itemDao().find("a")!!
        assertEquals("Updated", a.title)
        assertEquals(2, a.version)
        assertEquals(12.0, a.audioPositionSec, 0.0)
        assertEquals(3, a.stateSeq)
        assertNull(api.requestedCursors.first())
        assertEquals("1", api.requestedCursors[1])
    }

    @Test
    fun olderStateDoesNotOverwriteNewerLocalState() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.statePages += SyncStateDto(
            items = listOf(
                SyncStateItemDto(
                    id = "a",
                    stateSeq = 10,
                    audioPositionSec = 99.0,
                    consumptionState = "in_progress",
                    lastConsumedAt = 10,
                )
            ),
            nextCursor = "10",
            hasMore = false,
            epoch = EPOCH,
        )
        engine().sync()

        api.manifestPages.clear()
        api.statePages.clear()
        api.manifestPages += manifest(items = emptyList(), cursor = "1")
        api.statePages += SyncStateDto(
            items = listOf(
                SyncStateItemDto(
                    id = "a",
                    stateSeq = 9,
                    audioPositionSec = 5.0,
                    consumptionState = "unstarted",
                    lastConsumedAt = 1,
                )
            ),
            nextCursor = "9",
            hasMore = false,
            epoch = EPOCH,
        )
        engine().sync()

        val a = database.itemDao().find("a")!!
        assertEquals(99.0, a.audioPositionSec, 0.0)
        assertEquals(10, a.stateSeq)
    }

    @Test
    fun tombstoneDeletesLocalItemAndFilesAndReviveRestoresIt() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        engine().sync()
        val artifact = database.artifactDao().find("a", "transcript")!!
        val file = fileStore.pathFor("a", "transcript", artifact.mime)
        file.writeText("downloaded")
        database.artifactDao().upsert(
            artifact.copy(localPath = file.absolutePath, downloadState = "completed", downloadedBytes = 10)
        )

        api.manifestPages.clear()
        api.manifestPages += ManifestDto(
            items = emptyList(),
            tombstones = listOf(
                TombstoneDto(id = "a", version = 2, deletedAt = 20, epoch = EPOCH)
            ),
            nextCursor = "2",
            hasMore = false,
            epoch = EPOCH,
        )
        engine().sync()
        assertNull(database.itemDao().find("a"))
        assertFalse(file.exists())

        api.manifestPages.clear()
        api.manifestPages += manifest(items = listOf(item("a", version = 3)), cursor = "3")
        engine().sync()
        assertNotNull(database.itemDao().find("a"))
        assertEquals("none", database.artifactDao().find("a", "transcript")?.downloadState)
    }

    @Test
    fun reviveReplaysStateThatWasHiddenByTombstone() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.statePages += SyncStateDto(
            items = listOf(
                SyncStateItemDto(
                    id = "a",
                    stateSeq = 5,
                    audioPositionSec = 50.0,
                    consumptionState = "in_progress",
                    lastConsumedAt = 10,
                )
            ),
            nextCursor = "5",
            hasMore = false,
            epoch = EPOCH,
        )
        engine().sync()

        api.manifestPages.clear()
        api.statePages.clear()
        api.manifestPages += ManifestDto(
            items = emptyList(),
            tombstones = listOf(TombstoneDto("a", 2, 20, EPOCH)),
            nextCursor = "2",
            hasMore = false,
            epoch = EPOCH,
        )
        engine().sync()
        assertNull(database.itemDao().find("a"))

        api.manifestPages.clear()
        api.statePages.clear()
        api.manifestPages += manifest(items = listOf(item("a", version = 3)), cursor = "3")
        api.statePages += SyncStateDto(
            items = listOf(
                SyncStateItemDto(
                    id = "a",
                    stateSeq = 5,
                    audioPositionSec = 50.0,
                    consumptionState = "in_progress",
                    lastConsumedAt = 10,
                )
            ),
            nextCursor = "5",
            hasMore = false,
            epoch = EPOCH,
        )
        engine().sync()

        assertEquals(50.0, database.itemDao().find("a")?.audioPositionSec ?: 0.0, 0.0)
        assertEquals(5L, database.itemDao().find("a")?.stateSeq)
    }

    @Test
    fun epochChangeTriggersFullResyncAndRemovesMissingItems() = runBlocking {
        api.manifestPages += manifest(
            items = listOf(item("a", version = 1), item("c", version = 1)),
            cursor = "2",
        )
        api.statePages += state(items = emptyList(), cursor = "0")
        engine().sync()

        api.manifestPages.clear()
        api.statePages.clear()
        val newEpoch = manifest(items = listOf(item("a", version = 2)), cursor = "2", epoch = "epoch-2")
        api.manifestPages += newEpoch
        api.manifestPages += newEpoch
        api.statePages += state(items = emptyList(), cursor = "0", epoch = "epoch-2")
        val result = engine().sync()

        assertTrue(result.success)
        assertNotNull(database.itemDao().find("a"))
        assertNull(database.itemDao().find("c"))
        assertEquals("epoch-2", database.syncCursorDao().current()?.epoch)
    }

    @Test
    fun cursorInvalidRetriesOnceFromScratch() = runBlocking {
        api.failCursor = true
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.statePages += state(items = emptyList(), cursor = "0")

        val result = engine().sync()

        assertTrue(result.success)
        assertNotNull(database.itemDao().find("a"))
        assertEquals(listOf(null, null), api.requestedCursors)
    }

    @Test
    fun stateCursorInvalidTriggersFullResync() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.stateFailOnce = true
        api.statePages += state(items = emptyList(), cursor = "0")

        val result = engine().sync()

        assertTrue(result.success)
        assertEquals(listOf(null, null), api.requestedCursors)
        assertNotNull(database.itemDao().find("a"))
    }

    @Test
    fun partialFullResyncFailureRetriesFullAndReconcilesDeletedItems() = runBlocking {
        api.manifestPages += manifest(
            items = listOf(item("a", version = 1), item("ghost", version = 1)),
            cursor = "2",
        )
        api.statePages += state(items = emptyList(), cursor = "0")
        engine().sync()
        assertNotNull(database.itemDao().find("ghost"))

        api.manifestPages.clear()
        api.statePages.clear()
        api.manifestCallCount = 0
        api.manifestFailCall = 2
        api.manifestPages += manifest(items = listOf(item("a", version = 2)), cursor = "1", hasMore = true, epoch = "epoch-2")
        api.manifestPages += manifest(items = emptyList(), cursor = "2", epoch = "epoch-2")
        val failed = engine().sync()
        assertFalse(failed.success)
        assertNotNull(database.itemDao().find("ghost"))

        api.manifestFailCall = null
        api.manifestCallCount = 0
        api.manifestPages.clear()
        api.manifestPages += manifest(items = listOf(item("a", version = 2)), cursor = "1", epoch = "epoch-2")
        api.manifestPages += manifest(items = emptyList(), cursor = "2", epoch = "epoch-2")
        api.statePages += state(items = emptyList(), cursor = "0", epoch = "epoch-2")
        val recovered = engine().sync()

        assertTrue(recovered.success)
        assertNull(database.itemDao().find("ghost"))
        assertNotNull(database.itemDao().find("a"))
    }

    @Test
    fun downloadedFileIsReusedAcrossEpochResync() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.statePages += state(items = emptyList(), cursor = "0")
        engine().sync()
        val artifact = database.artifactDao().find("a", "transcript")!!
        val file = fileStore.pathFor("a", "transcript", artifact.mime)
        file.writeText("downloaded")
        database.artifactDao().upsert(
            artifact.copy(
                localPath = file.absolutePath,
                downloadState = "completed",
                downloadedBytes = 10,
            )
        )

        api.manifestPages.clear()
        api.statePages.clear()
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1", epoch = "epoch-2")
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1", epoch = "epoch-2")
        api.statePages += state(items = emptyList(), cursor = "0", epoch = "epoch-2")
        val result = engine().sync()

        assertTrue(result.success)
        val after = database.artifactDao().find("a", "transcript")!!
        assertEquals("completed", after.downloadState)
        assertEquals(file.absolutePath, after.localPath)
        assertTrue(file.exists())
    }

    @Test
    fun pendingMutationsSurviveEpochResetAndArePushed() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.statePages += state(items = emptyList(), cursor = "0")
        engine().sync()
        database.pendingMutationDao().upsert(
            PendingMutationEntity(
                idempotencyKey = "key-1",
                itemId = "a",
                field = "audio_progress",
                payloadJson = """{"position_sec":20.0}""",
                clientUpdatedAt = 999,
                createdAt = 999,
            )
        )
        api.progressResponse = MutationResponseDto(
            ok = true,
            item = MutationItemDto(id = "a", version = 2, audioPositionSec = 25.0),
        )

        api.manifestPages.clear()
        api.statePages.clear()
        api.progressFailOnce = true
        api.manifestPages += manifest(items = emptyList(), cursor = "0", epoch = "epoch-2")
        api.manifestPages += manifest(items = listOf(item("a", version = 2)), cursor = "1", hasMore = true, epoch = "epoch-2")
        api.manifestPages += manifest(items = emptyList(), cursor = "2", epoch = "epoch-2")
        api.statePages += state(items = emptyList(), cursor = "0", epoch = "epoch-2")
        val result = engine().sync()

        assertTrue(result.success)
        assertEquals(listOf("key-1", "key-1"), api.progressCalls.map { it.idempotencyKey })
        assertEquals(0, database.pendingMutationDao().count())
        assertEquals(25.0, database.itemDao().find("a")!!.audioPositionSec, 0.0)
    }

    @Test
    fun changedPausedArtifactStaysSelectedAndIsRequeued() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        engine().sync()
        val old = database.artifactDao().find("a", "transcript")!!
        database.artifactDao().upsert(old.copy(downloadState = "paused", downloadedBytes = 4))
        val enqueued = mutableListOf<String>()

        api.manifestPages.clear()
        api.manifestPages += manifest(
            items = listOf(
                item("a", version = 2, files = listOf(file("transcript", sha = "b".repeat(64))))
            ),
            cursor = "2",
        )
        engine(
            downloadQueue = object : DownloadQueue {
                override suspend fun enqueue(itemId: String) {
                    enqueued += itemId
                }
            }
        ).sync()

        val updated = database.artifactDao().find("a", "transcript")!!
        assertEquals("queued", updated.downloadState)
        assertEquals(listOf("a"), enqueued)
    }

    @Test
    fun newArtifactKindForSelectedItemIsQueued() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        engine().sync()
        val old = database.artifactDao().find("a", "transcript")!!
        database.artifactDao().upsert(old.copy(downloadState = "completed", localPath = "/tmp/a"))
        val enqueued = mutableListOf<String>()

        api.manifestPages.clear()
        api.manifestPages += manifest(
            items = listOf(
                item(
                    "a",
                    version = 2,
                    files = listOf(file("transcript"), file("audio")),
                )
            ),
            cursor = "2",
        )
        engine(
            downloadQueue = object : DownloadQueue {
                override suspend fun enqueue(itemId: String) {
                    enqueued += itemId
                }
            }
        ).sync()

        assertEquals("queued", database.artifactDao().find("a", "audio")!!.downloadState)
        assertEquals(listOf("a"), enqueued)
    }

    @Test
    fun pendingProgressIsPushedBeforePullAndCanonicalValueWins() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.statePages += state(items = emptyList(), cursor = "0")
        val sync = engine()
        sync.sync()

        api.calls.clear()
        api.manifestPages += manifest(items = emptyList(), cursor = "1")
        api.statePages += state(items = emptyList(), cursor = "0")
        api.progressResponse = MutationResponseDto(
            ok = true,
            applied = true,
            item = MutationItemDto(
                id = "a",
                version = 3,
                audioPositionSec = 21.0,
                consumptionState = "in_progress",
            ),
        )
        database.pendingMutationDao().upsert(
            PendingMutationEntity(
                idempotencyKey = "key-1",
                itemId = "a",
                field = "audio_progress",
                payloadJson = """{"position_sec":20.0,"consumption_state":"in_progress"}""",
                clientUpdatedAt = 999,
                createdAt = 999,
            )
        )

        val result = sync.sync()

        assertTrue(result.success)
        assertEquals(1, api.progressCalls.size)
        assertEquals("key-1", api.progressCalls.single().idempotencyKey)
        assertEquals(21.0, database.itemDao().find("a")?.audioPositionSec ?: 0.0, 0.0)
        assertEquals(0, database.pendingMutationDao().count())
        assertEquals(listOf("progress", "manifest", "state"), api.calls)
    }

    @Test
    fun pendingTagPushAppliesCanonicalTagsAndReportsConflict() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.statePages += state(items = emptyList(), cursor = "0")
        val sync = engine()
        sync.sync()

        api.calls.clear()
        api.manifestPages += manifest(items = emptyList(), cursor = "1")
        api.statePages += state(items = emptyList(), cursor = "0")
        api.tagsResponse = MutationResponseDto(
            ok = true,
            applied = false,
            item = MutationItemDto(
                id = "a",
                version = 4,
                tags = listOf("canonical"),
            ),
        )
        database.pendingMutationDao().upsert(
            PendingMutationEntity(
                idempotencyKey = "tags-1",
                itemId = "a",
                field = "tags",
                payloadJson = """{"tags":["stale"]}""",
                clientUpdatedAt = 999,
                createdAt = 999,
            )
        )

        val conflict = async { withTimeout(5_000) { sync.conflicts.first() } }
        val result = sync.sync()

        assertTrue(result.success)
        assertEquals(1, api.tagsCalls.size)
        assertEquals(listOf("canonical"), database.itemDao().findDetails("a")!!.tags.map { it.name })
        assertEquals(0, database.pendingMutationDao().count())
        assertTrue(conflict.await().contains("其他设备"))
        assertEquals(listOf("tags", "manifest", "state"), api.calls)
    }

    @Test
    fun failedPendingPushStillPullsManifestAndKeepsMutation() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.statePages += state(items = emptyList(), cursor = "0")
        api.progressError = TroveApiException("server.error", "boom", 500)
        database.pendingMutationDao().upsert(
            PendingMutationEntity(
                idempotencyKey = "key-1",
                itemId = "a",
                field = "audio_progress",
                payloadJson = """{"position_sec":20.0}""",
                clientUpdatedAt = 999,
                createdAt = 999,
            )
        )
        val sync = engine()

        val result = sync.sync()

        assertFalse(result.success)
        assertEquals(1, database.pendingMutationDao().count())
        assertTrue(api.calls.contains("manifest"))
        assertFalse(api.calls.contains("state"))
        assertNotNull(database.itemDao().find("a"))
        assertEquals(SyncStatus.Error("server.error", "boom", null), sync.status.value)
    }

    @Test
    fun failedPushDoesNotBlockOtherPendingMutations() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.statePages += state(items = emptyList(), cursor = "0")
        engine().sync()
        api.calls.clear()
        api.manifestPages.clear()
        api.manifestPages += manifest(items = emptyList(), cursor = "1")
        api.progressError = TroveApiException("server.error", "boom", 500)
        api.tagsResponse = MutationResponseDto(
            ok = true,
            item = MutationItemDto(id = "a", version = 2, tags = listOf("ok")),
        )
        database.pendingMutationDao().upsert(
            PendingMutationEntity(
                idempotencyKey = "progress-1",
                itemId = "a",
                field = "audio_progress",
                payloadJson = """{"position_sec":20.0}""",
                clientUpdatedAt = 998,
                createdAt = 998,
            )
        )
        database.pendingMutationDao().upsert(
            PendingMutationEntity(
                idempotencyKey = "tags-1",
                itemId = "a",
                field = "tags",
                payloadJson = """{"tags":["ok"]}""",
                clientUpdatedAt = 999,
                createdAt = 999,
            )
        )

        val result = engine().sync()

        assertFalse(result.success)
        assertEquals(1, api.tagsCalls.size)
        assertEquals(1, database.pendingMutationDao().count())
        assertEquals(listOf("ok"), database.itemDao().findDetails("a")!!.tags.map { it.name })
    }

    @Test
    fun retryReusesTheSameIdempotencyKey() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.progressResponse = MutationResponseDto(
            ok = true,
            item = MutationItemDto(id = "a", version = 2, audioPositionSec = 21.0),
        )
        api.progressError = TroveNetworkException("offline")
        database.pendingMutationDao().upsert(
            PendingMutationEntity(
                idempotencyKey = "stable-key",
                itemId = "a",
                field = "audio_progress",
                payloadJson = """{"position_sec":20.0}""",
                clientUpdatedAt = 999,
                createdAt = 999,
            )
        )
        val sync = engine()
        val first = sync.sync()
        assertFalse(first.success)
        assertEquals(1, database.pendingMutationDao().count())

        api.progressError = null
        api.manifestPages.clear()
        api.manifestPages += manifest(items = emptyList(), cursor = "1")
        api.statePages += state(items = emptyList(), cursor = "0")
        val second = sync.sync()

        assertTrue(second.success)
        assertEquals(0, database.pendingMutationDao().count())
        assertEquals(
            listOf("stable-key", "stable-key"),
            api.progressCalls.map { it.idempotencyKey },
        )
    }

    @Test
    fun clockSkewWarningIsVisibleAsNonBlockingNotice() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        api.progressResponse = MutationResponseDto(
            ok = true,
            item = MutationItemDto(id = "a", version = 2, audioPositionSec = 21.0),
            warnings = listOf("sync.clock_skew"),
        )
        database.pendingMutationDao().upsert(
            PendingMutationEntity(
                idempotencyKey = "key-1",
                itemId = "a",
                field = "audio_progress",
                payloadJson = """{"position_sec":20.0}""",
                clientUpdatedAt = 999,
                createdAt = 999,
            )
        )
        val sync = engine()
        val notice = async { withTimeout(5_000) { sync.conflicts.first() } }

        val result = sync.sync()

        assertTrue(result.success)
        assertTrue(notice.await().contains("时钟"))
    }

    @Test
    fun canonicalResponseDoesNotOverwriteANewerPendingField() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        engine().sync()
        api.manifestPages.clear()
        api.manifestPages += manifest(items = emptyList(), cursor = "1")
        api.tagsResponse = MutationResponseDto(
            ok = true,
            item = MutationItemDto(
                id = "a",
                version = 4,
                audioPositionSec = 5.0,
                consumptionState = "finished",
                tags = listOf("canonical"),
            ),
        )
        database.pendingMutationDao().upsert(
            PendingMutationEntity(
                idempotencyKey = "tags-1",
                itemId = "a",
                field = "tags",
                payloadJson = """{"tags":["local"]}""",
                clientUpdatedAt = 999,
                createdAt = 999,
            )
        )

        engine().sync()

        val a = database.itemDao().find("a")!!
        assertEquals(0.0, a.audioPositionSec, 0.0)
        assertEquals("unstarted", a.consumptionState)
        assertEquals(4, a.version)
        assertEquals(listOf("canonical"), database.itemDao().findDetails("a")!!.tags.map { it.name })
    }

    @Test
    fun offlineHostReportsOfflineStatusAndKeepsLastSuccess() = runBlocking {
        api.manifestError = TroveNetworkException("offline")
        val sync = engine()
        val result = sync.sync()
        assertFalse(result.success)
        assertEquals("sync.offline", result.errorCode)
        assertTrue(sync.status.value is SyncStatus.Offline)
    }

    @Test
    fun changedArtifactShaDropsOldFileAndRequeuesDownload() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        engine().sync()
        val old = database.artifactDao().find("a", "transcript")!!
        val oldFile = fileStore.pathFor("a", "transcript", old.mime)
        oldFile.writeText("old")
        database.artifactDao().upsert(
            old.copy(localPath = oldFile.absolutePath, downloadState = "completed", downloadedBytes = 3)
        )
        val enqueued = mutableListOf<String>()

        api.manifestPages.clear()
        api.manifestPages += manifest(
            items = listOf(
                item(
                    "a",
                    version = 2,
                    files = listOf(file("transcript", sha = "b".repeat(64))),
                )
            ),
            cursor = "2",
        )
        engine(
            downloadQueue = object : DownloadQueue {
                override suspend fun enqueue(itemId: String) {
                    enqueued += itemId
                }
            }
        ).sync()

        val updated = database.artifactDao().find("a", "transcript")!!
        assertEquals("b".repeat(64), updated.sha256)
        assertEquals("queued", updated.downloadState)
        assertNull(updated.localPath)
        assertFalse(oldFile.exists())
        assertEquals(listOf("a"), enqueued)
    }

    @Test
    fun changedTranscriptClearsParsedSegments() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        engine().sync()
        database.transcriptSegmentDao().insertAll(
            listOf(
                dev.trove.core.db.TranscriptSegmentEntity(
                    itemId = "a",
                    seq = 0,
                    startMs = 0,
                    endMs = 10,
                    text = "old",
                )
            )
        )

        api.manifestPages.clear()
        api.manifestPages += manifest(
            items = listOf(
                item("a", version = 2, files = listOf(file("transcript", sha = "b".repeat(64))))
            ),
            cursor = "2",
        )
        engine().sync()

        assertEquals(0, database.transcriptSegmentDao().countForItem("a"))
    }

    @Test
    fun deletedArtifactFileIsRemoved() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        engine().sync()
        val artifact = database.artifactDao().find("a", "transcript")!!
        val file = fileStore.pathFor("a", "transcript", artifact.mime)
        file.writeText("downloaded")
        database.artifactDao().upsert(artifact.copy(localPath = file.absolutePath, downloadState = "completed"))

        api.manifestPages.clear()
        api.manifestPages += manifest(
            items = listOf(item("a", version = 2, files = listOf(file("audio")))),
            cursor = "2",
        )
        engine().sync()

        assertNull(database.artifactDao().find("a", "transcript"))
        assertFalse(file.exists())
    }

    @Test
    fun tombstoneOfPlayingItemDefersFileDeletion() = runBlocking {
        api.manifestPages += manifest(items = listOf(item("a", version = 1)), cursor = "1")
        engine().sync()
        val artifact = database.artifactDao().find("a", "transcript")!!
        val file = fileStore.pathFor("a", "transcript", artifact.mime)
        file.writeText("downloaded")
        database.artifactDao().upsert(artifact.copy(localPath = file.absolutePath, downloadState = "completed"))

        api.manifestPages.clear()
        api.manifestPages += ManifestDto(
            items = emptyList(),
            tombstones = listOf(TombstoneDto("a", 2, 20, EPOCH)),
            nextCursor = "2",
            hasMore = false,
            epoch = EPOCH,
        )
        engine(nowPlaying = { "a" }).sync()

        assertNull(database.itemDao().find("a"))
        assertTrue(file.exists())
        assertEquals(1, database.pendingDeletionDao().all().size)
    }

    private fun manifest(
        items: List<SyncItemDto>,
        cursor: String,
        hasMore: Boolean = false,
        epoch: String = EPOCH,
    ) = ManifestDto(items = items, tombstones = emptyList(), nextCursor = cursor, hasMore = hasMore, epoch = epoch)

    private fun state(
        items: List<SyncStateItemDto>,
        cursor: String,
        epoch: String = EPOCH,
    ) = SyncStateDto(items = items, nextCursor = cursor, hasMore = false, epoch = epoch)

    private fun item(
        id: String,
        version: Int,
        title: String = "Item $id",
        files: List<SyncFileDto> = listOf(file("transcript")),
    ) = SyncItemDto(
        id = id,
        version = version,
        sourceType = "video_url",
        platform = "youtube",
        title = title,
        author = "作者",
        publishedAt = "2026-10-01",
        fetchedAt = 1_790_000_000_000,
        language = "zh",
        durationSec = 100.0,
        summary = "summary",
        tags = listOf("AI", "记忆"),
        processingState = "completed",
        hasAudio = true,
        hasBook = false,
        files = files,
    )

    private fun file(kind: String, sha: String = "a".repeat(64)) = SyncFileDto(
        kind = kind,
        sha256 = sha,
        size = 100,
        mime = if (kind == "transcript") "application/json" else "audio/mp4",
        version = 1,
        url = "/api/items/a/files/$kind",
    )

    private class ProgressCall(
        val request: ProgressRequestDto,
        val idempotencyKey: String?,
    )

    private class QueueApi : TroveApi {
        val manifestPages = ArrayDeque<ManifestDto>()
        val statePages = ArrayDeque<SyncStateDto>()
        val requestedCursors = mutableListOf<String?>()
        val calls = mutableListOf<String>()
        val progressCalls = mutableListOf<ProgressCall>()
        val tagsCalls = mutableListOf<Pair<String, TagsRequestDto>>()
        var failCursor = false
        var stateFailOnce = false
        var manifestCallCount = 0
        var manifestFailCall: Int? = null
        var manifestError: Throwable? = null
        var stateError: Throwable? = null
        var progressError: Throwable? = null
        var progressFailOnce = false
        var tagsError: Throwable? = null
        var progressResponse: MutationResponseDto? = null
        var tagsResponse: MutationResponseDto? = null
        private var cursorFailed = false

        override suspend fun health(): HealthDto = HealthDto()

        override suspend fun deviceToken(request: DeviceTokenRequest): DeviceTokenResponse =
            error("not used")

        override suspend fun devices(): DeviceListResponse = DeviceListResponse()

        override suspend fun revokeDevice(deviceId: String): Response<Unit> = Response.success(Unit)

        override suspend fun manifest(cursor: String?, limit: Int): ManifestDto {
            calls += "manifest"
            requestedCursors += cursor
            manifestCallCount += 1
            if (manifestFailCall == manifestCallCount) {
                throw TroveNetworkException("offline")
            }
            manifestError?.let { throw it }
            if (failCursor && !cursorFailed) {
                cursorFailed = true
                throw TroveApiException(CURSOR_INVALID, "invalid", 422)
            }
            return manifestPages.removeFirst()
        }

        override suspend fun state(cursor: String?, limit: Int): SyncStateDto {
            calls += "state"
            if (stateFailOnce) {
                stateFailOnce = false
                throw TroveApiException(CURSOR_INVALID, "invalid", 422)
            }
            stateError?.let { throw it }
            return if (statePages.isEmpty()) {
                SyncStateDto(emptyList(), "0", false, EPOCH)
            } else {
                statePages.removeFirst()
            }
        }

        override suspend fun progress(
            itemId: String,
            body: ProgressRequestDto,
            idempotencyKey: String?,
        ): MutationResponseDto {
            calls += "progress"
            progressCalls += ProgressCall(body, idempotencyKey)
            if (progressFailOnce) {
                progressFailOnce = false
                throw TroveApiException("server.error", "boom", 500)
            }
            progressError?.let { throw it }
            return progressResponse ?: MutationResponseDto(item = MutationItemDto(itemId))
        }

        override suspend fun tags(
            itemId: String,
            body: TagsRequestDto,
            idempotencyKey: String?,
        ): MutationResponseDto {
            calls += "tags"
            tagsCalls += itemId to body
            tagsError?.let { throw it }
            return tagsResponse ?: MutationResponseDto(item = MutationItemDto(itemId))
        }

        override suspend fun createItem(body: ItemCreateRequestDto): ItemCreateResponseDto =
            error("not used")

        override suspend fun item(itemId: String): ItemDto = error("not used")

        override suspend fun retryItem(itemId: String): ItemDto = error("not used")

        override suspend fun previewFeed(body: FeedPreviewRequestDto): FeedPreviewResponseDto =
            error("not used")

        override suspend fun search(
            query: String,
            type: String?,
            consumption: String?,
            tag: String?,
            source: String?,
            limit: Int,
        ): SearchResponseDto = error("not used")

        override suspend fun deleteItem(itemId: String): Response<Unit> = Response.success(Unit)
    }

    private companion object {
        const val EPOCH = "epoch-1"
    }
}
