package dev.trove.app

import android.content.Context
import androidx.lifecycle.viewModelScope
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.player.PlayerViewModel
import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.TestAppContainer
import dev.trove.core.auth.StoredCredential
import dev.trove.core.db.PendingDeletionEntity
import dev.trove.core.network.ManifestDto
import dev.trove.core.network.MutationItemDto
import dev.trove.core.network.MutationResponseDto
import dev.trove.core.network.SyncFileDto
import dev.trove.core.network.SyncItemDto
import dev.trove.core.network.SyncStateDto
import dev.trove.core.network.SyncStateItemDto
import dev.trove.core.network.TombstoneDto
import dev.trove.core.network.TroveNetworkException
import dev.trove.core.storage.ArtifactFileStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertEquals
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

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class SyncHardeningFlowTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    private lateinit var context: Context
    private lateinit var container: TestAppContainer
    private val playerViewModels = mutableListOf<PlayerViewModel>()

    @Before
    fun setUp() {
        Dispatchers.setMain(Dispatchers.Unconfined)
        context = ApplicationProvider.getApplicationContext()
        container = newContainer()
    }

    @After
    fun tearDown() {
        playerViewModels.forEach { it.viewModelScope.cancel() }
        container.close()
        container.database.close()
        Dispatchers.resetMain()
    }

    private fun playerViewModel(): PlayerViewModel =
        PlayerViewModel(
            repository = container.libraryRepository,
            player = container.fakePlayer,
            downloadManager = container.downloadManager,
            settingsStore = container.settingsStore,
            transcriptRepository = container.transcriptRepository,
            sessionController = container.sessionController,
            itemMutationRepository = container.itemMutationRepository,
            localSearchRepository = container.localSearchRepository,
            syncEngine = container.syncEngine,
        ).also { playerViewModels += it }

    private fun newContainer() =
        TestAppContainer(
            context = context,
            tokenStore = FakeTokenStore(
                StoredCredential("token", "device-1", "Pixel")
            ),
            settingsStore = FakeSettingsStore("https://host.example"),
            fileStore = ArtifactFileStore(temporaryFolder.newFolder()),
        ).also { container ->
            container.api.manifestResponse = ManifestDto(
                items = emptyList(),
                tombstones = emptyList(),
                nextCursor = "0",
                hasMore = false,
                epoch = EPOCH,
            )
            container.api.stateResponse = SyncStateDto(
                items = emptyList(),
                nextCursor = "0",
                hasMore = false,
                epoch = EPOCH,
            )
        }

    private suspend fun signInAndSync() {
        container.sessionController.restore()
        container.syncEngine.sync()
    }

    @Test
    fun offlineEditsQueueThenConvergeWithCanonicalConflict() = runBlocking {
        container.api.manifestPages += manifest(listOf(item("a", version = 1)), cursor = "1")
        container.api.statePages += state(emptyList(), cursor = "0")
        signInAndSync()
        container.api.manifestError = TroveNetworkException("offline")

        container.itemMutationRepository.setConsumption("a", "finished")
        container.itemMutationRepository.replaceTags("a", listOf("offline"))

        assertEquals(2, container.syncEngine.pendingMutationCount())
        assertEquals("finished", container.database.itemDao().find("a")!!.consumptionState)
        assertEquals(
            listOf("offline"),
            container.database.itemDao().findDetails("a")!!.tags.map { it.name },
        )

        container.api.manifestError = null
        container.api.manifestPages.clear()
        container.api.manifestPages += manifest(emptyList(), cursor = "1")
        container.api.statePages.clear()
        container.api.statePages += state(emptyList(), cursor = "0")
        container.api.progressResponse = MutationResponseDto(
            ok = true,
            applied = true,
            item = MutationItemDto(
                id = "a",
                version = 3,
                audioPositionSec = 12.0,
                consumptionState = "finished",
            ),
        )
        container.api.tagsResponse = MutationResponseDto(
            ok = true,
            applied = false,
            item = MutationItemDto(id = "a", version = 4, tags = listOf("host-wins")),
        )
        val notice = async {
            withTimeout(5_000) { container.syncEngine.conflicts.first() }
        }

        val result = container.syncEngine.sync()

        assertTrue(result.success)
        assertEquals(0, container.syncEngine.pendingMutationCount())
        assertEquals("finished", container.database.itemDao().find("a")!!.consumptionState)
        assertEquals(
            listOf("host-wins"),
            container.database.itemDao().findDetails("a")!!.tags.map { it.name },
        )
        assertTrue(notice.await().contains("其他设备"))
    }

    @Test
    fun failedPushRetriesWithTheSameIdempotencyKey() = runBlocking {
        container.api.manifestPages += manifest(listOf(item("a", version = 1)), cursor = "1")
        container.api.statePages += state(emptyList(), cursor = "0")
        signInAndSync()
        container.itemMutationRepository.setConsumption("a", "finished")
        val key = container.database.pendingMutationDao().pending().single().idempotencyKey
        container.api.progressFailuresRemaining = 1

        val first = container.syncEngine.sync()
        assertTrue(!first.success)
        assertEquals(1, container.syncEngine.pendingMutationCount())

        container.api.manifestPages.clear()
        container.api.manifestPages += manifest(emptyList(), cursor = "1")
        container.api.statePages.clear()
        container.api.statePages += state(emptyList(), cursor = "0")
        val second = container.syncEngine.sync()

        assertTrue(second.success)
        assertEquals(0, container.syncEngine.pendingMutationCount())
        assertEquals(listOf(key, key), container.api.progressKeys)
    }

    @Test
    fun epochChangeResyncsAndTombstoneThenReviveCleansLocalState() = runBlocking {
        container.api.manifestPages += manifest(
            listOf(item("a", version = 1), item("gone", version = 1)),
            cursor = "2",
        )
        container.api.statePages += state(emptyList(), cursor = "0")
        signInAndSync()
        assertNotNull(container.database.itemDao().find("gone"))

        container.api.manifestPages.clear()
        container.api.statePages.clear()
        container.api.manifestPages += manifest(
            emptyList(),
            cursor = "0",
            epoch = "epoch-2",
        )
        container.api.manifestPages += ManifestDto(
            items = emptyList(),
            tombstones = listOf(TombstoneDto("a", 2, 20, "epoch-2")),
            nextCursor = "3",
            hasMore = false,
            epoch = "epoch-2",
        )
        container.api.statePages += state(emptyList(), cursor = "0", epoch = "epoch-2")
        val result = container.syncEngine.sync()

        assertTrue(result.success)
        assertNull(container.database.itemDao().find("gone"))
        assertNull(container.database.itemDao().find("a"))

        container.api.manifestPages.clear()
        container.api.manifestPages += manifest(
            listOf(item("a", version = 3)),
            cursor = "4",
            epoch = "epoch-2",
        )
        container.api.statePages += state(
            listOf(
                SyncStateItemDto(
                    id = "a",
                    stateSeq = 9,
                    audioPositionSec = 77.0,
                    consumptionState = "in_progress",
                    lastConsumedAt = 100,
                )
            ),
            cursor = "9",
            epoch = "epoch-2",
        )
        container.syncEngine.sync()

        assertEquals(77.0, container.database.itemDao().find("a")!!.audioPositionSec, 0.0)
    }

    @Test
    fun reinstallRestoresLibraryAndProgressFromHost() = runBlocking {
        container.api.manifestPages += manifest(listOf(item("a", version = 1)), cursor = "1")
        container.api.statePages += state(
            listOf(
                SyncStateItemDto(
                    id = "a",
                    stateSeq = 5,
                    audioPositionSec = 42.0,
                    consumptionState = "in_progress",
                    lastConsumedAt = 10,
                )
            ),
            cursor = "5",
        )
        signInAndSync()
        val tokenStore = container.tokenStore as FakeTokenStore
        val settingsStore = container.settingsStore as FakeSettingsStore

        val reinstalled = TestAppContainer(
            context = context,
            api = container.api,
            tokenStore = tokenStore,
            settingsStore = settingsStore,
            fileStore = ArtifactFileStore(temporaryFolder.newFolder()),
        )
        try {
            reinstalled.sessionController.restore()
            reinstalled.api.manifestPages.clear()
            reinstalled.api.manifestPages += manifest(listOf(item("a", version = 1)), cursor = "1")
            reinstalled.api.statePages.clear()
            reinstalled.api.statePages += state(
                listOf(
                    SyncStateItemDto(
                        id = "a",
                        stateSeq = 5,
                        audioPositionSec = 42.0,
                        consumptionState = "in_progress",
                        lastConsumedAt = 10,
                    )
                ),
                cursor = "5",
            )
            val result = reinstalled.syncEngine.sync()

            assertTrue(result.success)
            val restored = reinstalled.database.itemDao().find("a")
            assertNotNull(restored)
            assertEquals(42.0, restored!!.audioPositionSec, 0.0)
            assertEquals(
                "none",
                reinstalled.database.artifactDao().find("a", "transcript")?.downloadState,
            )
        } finally {
            reinstalled.close()
            reinstalled.database.close()
        }
    }

    @Test
    fun tombstoneOfOpenItemIsReportedToPlayer() = runBlocking<Unit> {
        container.api.manifestPages += manifest(listOf(item("a", version = 1)), cursor = "1")
        container.api.statePages += state(emptyList(), cursor = "0")
        signInAndSync()
        val viewModel = playerViewModel()
        viewModel.open("a", autoPlay = false)
        withTimeout(5_000) { viewModel.state.first { it.item != null } }

        container.api.manifestPages.clear()
        container.api.manifestPages += ManifestDto(
            items = emptyList(),
            tombstones = listOf(TombstoneDto("a", 2, 20, EPOCH)),
            nextCursor = "2",
            hasMore = false,
            epoch = EPOCH,
        )
        container.syncEngine.sync()

        withTimeout(5_000) { viewModel.state.first { it.deleted } }
    }

    @Test
    fun finishedPlaybackCleansDeferredDeletion() = runBlocking<Unit> {
        container.api.manifestPages += manifest(
            listOf(item("a", version = 1, files = listOf(file("audio")))),
            cursor = "1",
        )
        container.api.statePages += state(emptyList(), cursor = "0")
        signInAndSync()
        val artifact = container.database.artifactDao().find("a", "audio")!!
        val file = container.fileStore.pathFor("a", "audio", artifact.mime)
        file.writeBytes(byteArrayOf(1, 2, 3))
        container.database.pendingDeletionDao().upsertAll(
            listOf(PendingDeletionEntity(file.absolutePath, "a"))
        )
        val viewModel = playerViewModel()
        viewModel.open("a", autoPlay = true)
        withTimeout(5_000) {
            while (container.fakePlayer.requests.isEmpty()) {
                kotlinx.coroutines.delay(10)
            }
        }

        container.fakePlayer.finish()

        withTimeout(5_000) {
            while (container.database.pendingDeletionDao().all().isNotEmpty()) {
                kotlinx.coroutines.delay(10)
            }
        }
        assertTrue(!file.exists())
    }

    @Test
    fun offlineHostStillPlaysDownloadedAudioAndQueuesProgress() = runBlocking {
        container.api.manifestPages += manifest(
            listOf(item("a", version = 1, files = listOf(file("audio")))),
            cursor = "1",
        )
        container.api.statePages += state(emptyList(), cursor = "0")
        signInAndSync()
        val artifact = container.database.artifactDao().find("a", "audio")!!
        val file = container.fileStore.pathFor("a", "audio", artifact.mime)
        file.writeBytes(byteArrayOf(1, 2, 3))
        container.database.artifactDao().upsert(
            artifact.copy(
                localPath = file.absolutePath,
                downloadState = "completed",
                downloadedBytes = 3,
            )
        )
        container.api.manifestError = TroveNetworkException("offline")

        val viewModel = playerViewModel()
        viewModel.open("a", autoPlay = true)

        withTimeout(5_000) {
            while (container.fakePlayer.requests.isEmpty()) {
                kotlinx.coroutines.delay(10)
            }
        }
        val request = container.fakePlayer.requests.single()
        assertTrue(request.url.startsWith("file:"))
        container.progressRecorder.savePosition("a", 3_000, ended = false)
        assertEquals(1, container.syncEngine.pendingMutationCount())
        assertEquals("in_progress", container.database.itemDao().find("a")!!.consumptionState)
    }

    private fun manifest(
        items: List<SyncItemDto>,
        cursor: String,
        epoch: String = EPOCH,
    ) = ManifestDto(
        items = items,
        tombstones = emptyList(),
        nextCursor = cursor,
        hasMore = false,
        epoch = epoch,
    )

    private fun state(
        items: List<SyncStateItemDto>,
        cursor: String,
        epoch: String = EPOCH,
    ) = SyncStateDto(
        items = items,
        nextCursor = cursor,
        hasMore = false,
        epoch = epoch,
    )

    private fun item(
        id: String,
        version: Int,
        files: List<SyncFileDto> = listOf(file("transcript")),
    ) = SyncItemDto(
        id = id,
        version = version,
        sourceType = "video_url",
        platform = "youtube",
        title = "Item $id",
        author = "作者",
        publishedAt = "2026-10-01",
        fetchedAt = 1_790_000_000_000,
        language = "zh",
        durationSec = 100.0,
        summary = "summary",
        tags = listOf("AI"),
        processingState = "completed",
        hasAudio = true,
        hasBook = false,
        files = files,
    )

    private fun file(kind: String) = SyncFileDto(
        kind = kind,
        sha256 = "a".repeat(64),
        size = 100,
        mime = if (kind == "transcript") "application/json" else "audio/mp4",
        version = 1,
        url = "/api/items/a/files/$kind",
    )

    private companion object {
        const val EPOCH = "epoch-1"
    }
}
