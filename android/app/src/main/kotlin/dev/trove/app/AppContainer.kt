package dev.trove.app

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import dev.trove.app.playback.PlaybackProgressRecorder
import dev.trove.app.session.SessionController
import dev.trove.app.session.SessionState
import dev.trove.app.add.firstSharedUrl
import dev.trove.app.sync.PeriodicSyncScheduler
import dev.trove.core.auth.KeystoreTokenStore
import dev.trove.core.auth.TokenStore
import dev.trove.core.db.TroveDatabase
import dev.trove.core.download.ArtifactDownloader
import dev.trove.core.download.DataStoreDownloadSettingsStore
import dev.trove.core.download.DefaultDownloadManager
import dev.trove.core.download.DownloadEnvironment
import dev.trove.core.download.DownloadEnvironmentHolder
import dev.trove.core.download.DownloadManager
import dev.trove.core.download.DownloadSettingsStore
import dev.trove.core.download.WorkManagerDownloadQueue
import dev.trove.core.library.LibraryRepository
import dev.trove.core.library.ItemMutationRepository
import dev.trove.core.network.RetrofitTroveApiFactory
import dev.trove.core.network.TroveApiFactory
import dev.trove.core.reading.BookRepository
import dev.trove.core.search.LocalSearchRepository
import dev.trove.core.search.SearchIndex
import dev.trove.core.settings.DataStoreSettingsStore
import dev.trove.core.settings.SettingsStore
import dev.trove.core.storage.ArtifactFileStore
import dev.trove.core.storage.LocalDataRepository
import dev.trove.core.sync.DownloadQueue
import dev.trove.core.sync.SyncEngine
import dev.trove.core.transcript.TranscriptRepository
import dev.trove.playback.MediaSessionPlayer
import dev.trove.playback.PlaybackEnvironment
import dev.trove.playback.PlayerGateway
import dev.trove.reader.ReaderDependencies
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

open class AppContainer(
    context: Context,
    val tokenStore: TokenStore = KeystoreTokenStore(context),
    val settingsStore: SettingsStore = DataStoreSettingsStore(context),
    val apiFactory: TroveApiFactory = RetrofitTroveApiFactory(),
    databaseOverride: TroveDatabase? = null,
    val fileStore: ArtifactFileStore = ArtifactFileStore(context.filesDir),
    val downloadSettingsStore: DownloadSettingsStore = DataStoreDownloadSettingsStore(context),
    downloadQueue: DownloadQueue = WorkManagerDownloadQueue(context, downloadSettingsStore),
    val player: PlayerGateway = MediaSessionPlayer(context),
    allowDebugCleartext: Boolean = BuildConfig.DEBUG,
    private val backgroundSyncEnabled: Boolean = true,
) {
    val database: TroveDatabase = databaseOverride ?: TroveDatabase.create(context)

    val sharedUrl = MutableStateFlow<String?>(null)

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val syncScheduler = PeriodicSyncScheduler(context)

    val sessionController: SessionController = SessionController(
        tokenStore = tokenStore,
        settingsStore = settingsStore,
        apiFactory = apiFactory,
        allowDebugCleartext = allowDebugCleartext,
        allowLanCleartext = BuildConfig.ALLOW_LAN_CLEARTEXT,
        scope = scope,
    )

    val libraryRepository = LibraryRepository(database, fileStore)

    val transcriptRepository = TranscriptRepository(database, fileStore)

    val bookRepository = BookRepository(database, fileStore)

    val searchIndex = SearchIndex(database)

    val localSearchRepository = LocalSearchRepository(
        database = database,
        transcriptRepository = transcriptRepository,
        bookRepository = bookRepository,
        index = searchIndex,
    )

    val itemMutationRepository = ItemMutationRepository(
        database = database,
        onTagsChanged = { itemId -> localSearchRepository.indexItem(itemId) },
    )

    val localDataRepository = LocalDataRepository(
        database = database,
        fileStore = fileStore,
        searchIndex = searchIndex,
    )

    val readerDependencies = ReaderDependencies(
        database = database,
        libraryRepository = libraryRepository,
        bookRepository = bookRepository,
        itemMutationRepository = itemMutationRepository,
    )

    val downloader = ArtifactDownloader(
        database = database,
        fileStore = fileStore,
        hostProvider = { settingsStore.hostUrl.first() },
        tokenProvider = { tokenStore.read()?.token },
        preferencesProvider = { downloadSettingsStore.preferences.first() },
        onUnauthorized = sessionController::onUnauthorized,
        nowPlayingItemId = ::currentPlayerItemId,
        onItemFilesChanged = { itemId -> localSearchRepository.indexItem(itemId) },
    )

    val downloadManager: DownloadManager = DefaultDownloadManager(
        database = database,
        downloader = downloader,
        queue = downloadQueue,
    )

    val syncEngine = SyncEngine(
        database = database,
        clientProvider = { sessionController.currentClient() },
        fileStore = fileStore,
        downloadQueue = downloadQueue,
        nowPlayingItemId = ::currentPlayerItemId,
        onItemChanged = { itemId -> localSearchRepository.indexItem(itemId) },
    )

    val progressRecorder = PlaybackProgressRecorder(database)

    fun offerSharedText(text: String?) {
        firstSharedUrl(text)?.let { sharedUrl.value = it }
    }

    fun consumeSharedUrl() {
        sharedUrl.value = null
    }

    /** Stop background collectors; used by tests before resetting Main. */
    internal fun close() {
        scope.cancel()
        player.release()
    }

    private fun currentPlayerItemId(): String? = player.state.value.itemId

    init {
        DownloadEnvironmentHolder.current = DownloadEnvironment(
            database = database,
            fileStore = fileStore,
            settingsStore = settingsStore,
            downloadSettings = downloadSettingsStore,
            tokenStore = tokenStore,
            onUnauthorized = sessionController::onUnauthorized,
            nowPlayingItemId = ::currentPlayerItemId,
            onItemFilesChanged = { itemId -> localSearchRepository.indexItem(itemId) },
        )
        PlaybackEnvironment.progressSink = progressRecorder
        PlaybackEnvironment.onUnauthorized = {
            sessionController.onUnauthorized("auth.device_token_invalid")
        }
        scope.launch {
            sessionController.restore()
        }
        scope.launch {
            if (localSearchRepository.isAvailable() && !searchIndex.hasDocuments()) {
                localSearchRepository.rebuild()
            }
        }
        scope.launch {
            sessionController.state.collect { state ->
                PlaybackEnvironment.token = (state as? SessionState.SignedIn)?.credential?.token
                if (state is SessionState.SignedIn) {
                    syncScheduler.apply(settingsStore.syncPreferences.first())
                    if (backgroundSyncEnabled) syncScheduler.syncNow()
                } else {
                    syncScheduler.cancel()
                }
                withContext(Dispatchers.Main) {
                    if (state is SessionState.SignedIn) {
                        player.connect()
                    } else {
                        player.release()
                    }
                }
            }
        }
        scope.launch {
            settingsStore.syncPreferences.collect { preferences ->
                if (sessionController.state.value is SessionState.SignedIn) {
                    syncScheduler.apply(preferences)
                }
            }
        }
        runCatching {
            context.applicationContext
                .getSystemService(ConnectivityManager::class.java)
                ?.registerDefaultNetworkCallback(
                    object : ConnectivityManager.NetworkCallback() {
                        override fun onAvailable(network: Network) {
                            if (backgroundSyncEnabled &&
                                sessionController.state.value is SessionState.SignedIn
                            ) {
                                syncScheduler.syncNow()
                            }
                        }
                    }
                )
        }
    }
}
