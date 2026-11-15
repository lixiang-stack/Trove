package dev.trove.app.settings

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.session.SessionController
import dev.trove.app.testing.FakeDownloadSettingsStore
import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.FakeTroveApi
import dev.trove.app.testing.FakeTroveApiFactory
import dev.trove.core.auth.StoredCredential
import dev.trove.core.db.ArtifactEntity
import dev.trove.core.db.ItemEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.download.DownloadPreferences
import dev.trove.core.network.HealthDto
import dev.trove.core.search.SearchIndex
import dev.trove.core.storage.ArtifactFileStore
import dev.trove.core.storage.LocalDataRepository
import dev.trove.core.sync.SyncEngine
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
class SettingsViewModelTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    private lateinit var database: TroveDatabase
    private lateinit var fileStore: ArtifactFileStore
    private lateinit var settings: FakeSettingsStore
    private lateinit var downloads: FakeDownloadSettingsStore
    private lateinit var tokenStore: FakeTokenStore
    private lateinit var api: FakeTroveApi
    private lateinit var controller: SessionController
    private lateinit var viewModel: SettingsViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(Dispatchers.Unconfined)
        val context = ApplicationProvider.getApplicationContext<Context>()
        database = TroveDatabase.inMemory(context)
        fileStore = ArtifactFileStore(temporaryFolder.newFolder("artifacts"))
        settings = FakeSettingsStore("https://host.example")
        downloads = FakeDownloadSettingsStore(DownloadPreferences(quotaBytes = 1_000))
        tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel"))
        api = FakeTroveApi()
        api.healthResponse = HealthDto(
            apiVersion = "1.2.3",
            capabilities = mapOf("sync" to true, "file_download" to true),
        )
        controller = SessionController(
            tokenStore = tokenStore,
            settingsStore = settings,
            apiFactory = FakeTroveApiFactory(api),
            allowDebugCleartext = false,
        )
        runBlocking { controller.restore() }
        viewModel = SettingsViewModel(
            settingsStore = settings,
            downloadSettings = downloads,
            syncEngine = SyncEngine(
                database = database,
                clientProvider = { controller.currentClient() },
                fileStore = fileStore,
            ),
            sessionController = controller,
            localData = LocalDataRepository(database, fileStore, SearchIndex(database)),
            localSearch = dev.trove.core.search.LocalSearchRepository(
                database = database,
                transcriptRepository = dev.trove.core.transcript.TranscriptRepository(database, fileStore),
                bookRepository = dev.trove.core.reading.BookRepository(database, fileStore),
                index = SearchIndex(database),
            ),
        )
    }

    @After
    fun tearDown() {
        database.close()
        Dispatchers.resetMain()
    }

    @Test
    fun syncPreferencesAndDiagnosticsAreExposed() {
        viewModel.setPeriodicEnabled(false)
        viewModel.setIntervalMinutes(30)
        waitFor { viewModel.state.value.syncPreferences.intervalMinutes == 30L }

        assertFalse(viewModel.state.value.syncPreferences.periodicEnabled)
        assertEquals("https://host.example", viewModel.state.value.hostUrl)
        waitFor { viewModel.state.value.diagnostics.apiVersion == "1.2.3" }
        assertEquals("1.2.3", viewModel.state.value.diagnostics.apiVersion)
        assertTrue(viewModel.state.value.diagnostics.capabilities.contains("sync"))
        assertFalse(viewModel.state.value.toString().contains("token"))
    }

    @Test
    fun clearingLocalDataDeletesItemsButKeepsSession() = runBlocking {
        database.itemDao().upsert(item("item-1"))
        database.artifactDao().upsert(
            ArtifactEntity(
                itemId = "item-1",
                kind = "audio",
                sha256 = "a".repeat(64),
                size = 10,
                mime = "audio/mp4",
                version = 1,
                localPath = null,
                downloadState = "completed",
            )
        )

        viewModel.clearLocalData()
        waitFor { viewModel.state.value.message != null }

        assertEquals(0, database.itemDao().count())
        assertEquals("token", tokenStore.credential?.token)
        assertTrue(viewModel.state.value.message!!.contains("已清除"))
    }

    @Test
    fun signOutClearsTokenButLeavesDownloads() = runBlocking {
        database.itemDao().upsert(item("item-1"))
        viewModel.signOut()
        waitFor { tokenStore.clearCalls > 0 }

        assertEquals(0, tokenStore.credential?.token?.length ?: 0)
        assertEquals(1, database.itemDao().count())
    }

    private fun waitFor(condition: () -> Boolean) {
        val deadline = System.currentTimeMillis() + 5_000
        while (!condition()) {
            if (System.currentTimeMillis() > deadline) error("condition not met")
            Thread.sleep(10)
        }
    }

    private fun item(id: String) = ItemEntity(
        id = id,
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
        consumptionState = "in_progress",
        audioPositionSec = 10.0,
        bookLocator = null,
        lastConsumedAt = 1,
        contentSeq = 1,
        stateSeq = 1,
        lastSyncedAt = 1,
    )
}
