package dev.trove.app.player

import android.content.Context
import androidx.lifecycle.viewModelScope
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.session.SessionController
import dev.trove.app.testing.FakeDownloadManager
import dev.trove.app.testing.FakePlayer
import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.FakeTroveApi
import dev.trove.app.testing.FakeTroveApiFactory
import dev.trove.app.testing.MainDispatcherRule
import dev.trove.core.auth.StoredCredential
import dev.trove.core.db.ArtifactEntity
import dev.trove.core.db.ItemEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.library.ItemMutationRepository
import dev.trove.core.library.LibraryRepository
import dev.trove.core.reading.BookRepository
import dev.trove.core.search.LocalSearchRepository
import dev.trove.core.search.SearchIndex
import dev.trove.core.storage.ArtifactFileStore
import dev.trove.core.sync.SyncEngine
import dev.trove.core.transcript.TranscriptRepository
import kotlinx.coroutines.cancel
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class PlayerViewModelTest {
    @get:Rule
    val mainDispatcher = MainDispatcherRule()

    @get:Rule
    val temporaryFolder = TemporaryFolder()

    private lateinit var database: TroveDatabase
    private lateinit var fileStore: ArtifactFileStore
    private lateinit var repository: LibraryRepository
    private lateinit var player: FakePlayer
    private lateinit var downloads: FakeDownloadManager
    private lateinit var api: FakeTroveApi
    private lateinit var controller: SessionController
    private lateinit var settingsStore: FakeSettingsStore
    private val viewModels = mutableListOf<PlayerViewModel>()

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        database = TroveDatabase.inMemory(context)
        fileStore = ArtifactFileStore(temporaryFolder.newFolder("artifacts"))
        repository = LibraryRepository(database, fileStore)
        player = FakePlayer()
        downloads = FakeDownloadManager()
        api = FakeTroveApi()
        settingsStore = FakeSettingsStore("https://host.example")
        controller = SessionController(
            tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel")),
            settingsStore = settingsStore,
            apiFactory = FakeTroveApiFactory(api),
            allowDebugCleartext = false,
        )
    }

    @After
    fun tearDown() {
        viewModels.forEach { it.viewModelScope.cancel() }
        database.close()
    }

    private fun viewModel() = PlayerViewModel(
        repository = repository,
        player = player,
        downloadManager = downloads,
        settingsStore = settingsStore,
        transcriptRepository = TranscriptRepository(database, fileStore),
        sessionController = controller,
        itemMutationRepository = ItemMutationRepository(database),
        localSearchRepository = LocalSearchRepository(
            database = database,
            transcriptRepository = TranscriptRepository(database, fileStore),
            bookRepository = BookRepository(database, fileStore),
            index = SearchIndex(database),
        ),
        syncEngine = SyncEngine(
            database = database,
            clientProvider = { controller.currentClient() },
            fileStore = fileStore,
        ),
    ).also { viewModels += it }

    @Test
    fun streamingPlaybackUsesHostFileUrlAndSavedPosition() = runBlocking {
        controller.restore()
        seedItem(audioPositionSec = 42.0)
        val model = viewModel()

        model.open("item-1", autoPlay = true)
        waitFor { player.requests.isNotEmpty() }

        val request = player.requests.single()
        assertEquals("https://host.example/api/items/item-1/files/audio", request.url)
        assertEquals(42_000, request.startPositionMs)
        assertEquals("Item", request.title)
        waitFor { model.state.value.playback.isPlaying }
        assertEquals("item-1", model.state.value.playback.itemId)
    }

    @Test
    fun downloadedAudioUsesLocalFileUri() = runBlocking {
        controller.restore()
        seedItem()
        val file = fileStore.pathFor("item-1", "audio", "audio/mp4")
        file.writeBytes(byteArrayOf(1, 2, 3))
        database.artifactDao().upsert(
            ArtifactEntity(
                itemId = "item-1",
                kind = "audio",
                sha256 = "a".repeat(64),
                size = 3,
                mime = "audio/mp4",
                version = 1,
                localPath = file.absolutePath,
                downloadState = "completed",
                downloadedBytes = 3,
            )
        )
        val model = viewModel()

        model.open("item-1", autoPlay = true)
        waitFor { player.requests.isNotEmpty() }

        assertTrue(player.requests.single().url.startsWith("file:"))
        assertFalse(player.requests.single().url.contains("host.example"))
    }

    @Test
    fun togglingSameItemDelegatesToPlayerWithoutRestarting() = runBlocking {
        controller.restore()
        seedItem()
        val model = viewModel()
        model.open("item-1", autoPlay = true)
        waitFor { player.requests.isNotEmpty() }
        waitFor {
            model.state.value.item != null &&
                model.state.value.playback.itemId == "item-1" &&
                model.state.value.playback.isPlaying
        }

        model.toggle()
        waitFor { !model.state.value.playback.isPlaying }

        assertEquals(1, player.requests.size)
    }

    @Test
    fun reopeningRouteWithoutAutoplayKeepsPausedPlayback() = runBlocking {
        controller.restore()
        seedItem()
        val model = viewModel()
        model.open("item-1", autoPlay = true)
        waitFor { player.requests.isNotEmpty() }
        waitFor {
            model.state.value.item != null &&
                model.state.value.playback.itemId == "item-1" &&
                model.state.value.playback.isPlaying
        }
        model.toggle()
        waitFor { !model.state.value.playback.isPlaying }

        model.open("item-1", autoPlay = false)
        Thread.sleep(100)

        assertFalse(model.state.value.playback.isPlaying)
        assertEquals(1, player.requests.size)
    }

    @Test
    fun speedChangesAndDownloadActionsAreDelegated() = runBlocking {
        controller.restore()
        seedItem()
        val model = viewModel()
        model.open("item-1", autoPlay = true)
        waitFor { player.requests.isNotEmpty() }
        waitFor { downloads.enqueued.isNotEmpty() }
        downloads.enqueued.clear()

        model.setSpeed(1.5f)
        model.download()
        model.pauseDownload()
        model.retryDownload()
        model.removeDownload()
        waitFor { downloads.removed.isNotEmpty() }

        assertEquals(listOf(1.5f), player.speeds)
        assertEquals(listOf("item-1"), downloads.enqueued)
        assertEquals(listOf("item-1"), downloads.paused)
        assertEquals(listOf("item-1"), downloads.retried)
        assertEquals(listOf("item-1"), downloads.removed)
    }

    @Test
    fun openingItemQueuesDownloadForAutomaticSync() = runBlocking {
        controller.restore()
        seedItem()
        val model = viewModel()

        model.open("item-1", autoPlay = false)
        waitFor { downloads.enqueued.contains("item-1") }

        assertEquals(listOf("item-1"), downloads.enqueued)
    }

    @Test
    fun autoSyncDoesNotOverridePausedDownload() = runBlocking {
        controller.restore()
        seedItem()
        database.artifactDao().setDownloadState("item-1", "audio", "paused", null)
        val model = viewModel()

        model.open("item-1", autoPlay = false)
        Thread.sleep(100)

        assertTrue(downloads.enqueued.isEmpty())
    }

    @Test
    fun deletingItemCallsHostAndRemovesLocalCopy() = runBlocking {
        controller.restore()
        seedItem()
        val model = viewModel()
        model.open("item-1", autoPlay = true)
        waitFor { player.requests.isNotEmpty() }

        model.deleteItem()
        waitFor { model.state.value.deleted }

        assertEquals(listOf("item-1"), api.deletedItems)
        assertNull(repository.find("item-1"))
    }

    @Test
    fun missingItemReportsReadableError() = runBlocking {
        controller.restore()
        val model = viewModel()

        model.open("missing", autoPlay = true)
        waitFor { model.state.value.errorCode != null }

        assertEquals("item.missing", model.state.value.errorCode)
        assertTrue(player.requests.isEmpty())
    }

    private fun waitFor(condition: () -> Boolean) {
        val deadline = System.currentTimeMillis() + 5_000
        while (!condition()) {
            if (System.currentTimeMillis() > deadline) {
                fail("condition not met")
            }
            Thread.sleep(10)
        }
    }

    private suspend fun seedItem(audioPositionSec: Double = 0.0) {
        database.itemDao().upsert(
            ItemEntity(
                id = "item-1",
                version = 1,
                sourceType = "video_url",
                platform = "youtube",
                title = "Item",
                author = "作者",
                publishedAt = null,
                fetchedAt = 1,
                language = "zh",
                durationSec = 100.0,
                summary = "Summary",
                processingState = "completed",
                errorCode = null,
                errorMessage = null,
                hasAudio = true,
                hasBook = false,
                consumptionState = "unstarted",
                audioPositionSec = audioPositionSec,
                bookLocator = null,
                lastConsumedAt = null,
                contentSeq = 1,
                stateSeq = 1,
                lastSyncedAt = 1,
            )
        )
        database.artifactDao().upsert(
            ArtifactEntity(
                itemId = "item-1",
                kind = "audio",
                sha256 = "a".repeat(64),
                size = 100,
                mime = "audio/mp4",
                version = 1,
                localPath = null,
                downloadState = "none",
            )
        )
    }
}
