package dev.trove.app

import android.content.Context
import dev.trove.app.playback.PlaybackProgressRecorder
import dev.trove.app.session.SessionController
import dev.trove.app.session.SessionState
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
import dev.trove.core.network.RetrofitTroveApiFactory
import dev.trove.core.network.TroveApiFactory
import dev.trove.core.settings.DataStoreSettingsStore
import dev.trove.core.settings.SettingsStore
import dev.trove.core.storage.ArtifactFileStore
import dev.trove.core.sync.DownloadQueue
import dev.trove.core.sync.SyncEngine
import dev.trove.core.transcript.TranscriptRepository
import dev.trove.playback.MediaSessionPlayer
import dev.trove.playback.PlaybackEnvironment
import dev.trove.playback.PlayerGateway
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
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
) {
    val database: TroveDatabase = databaseOverride ?: TroveDatabase.create(context)

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val sessionController: SessionController = SessionController(
        tokenStore = tokenStore,
        settingsStore = settingsStore,
        apiFactory = apiFactory,
        allowDebugCleartext = allowDebugCleartext,
        scope = scope,
    )

    val libraryRepository = LibraryRepository(database, fileStore)

    val transcriptRepository = TranscriptRepository(database, fileStore)

    val downloader = ArtifactDownloader(
        database = database,
        fileStore = fileStore,
        hostProvider = { settingsStore.hostUrl.first() },
        tokenProvider = { tokenStore.read()?.token },
        preferencesProvider = { downloadSettingsStore.preferences.first() },
        onUnauthorized = sessionController::onUnauthorized,
        nowPlayingItemId = {
            val playback = player.state.value
            playback.itemId?.takeIf { playback.isPlaying }
        },
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
        nowPlayingItemId = {
            val playback = player.state.value
            playback.itemId?.takeIf { playback.isPlaying }
        },
    )

    val progressRecorder = PlaybackProgressRecorder(database)

    init {
        DownloadEnvironmentHolder.current = DownloadEnvironment(
            database = database,
            fileStore = fileStore,
            settingsStore = settingsStore,
            downloadSettings = downloadSettingsStore,
            tokenStore = tokenStore,
            onUnauthorized = sessionController::onUnauthorized,
            nowPlayingItemId = {
                val playback = player.state.value
                playback.itemId?.takeIf { playback.isPlaying }
            },
        )
        PlaybackEnvironment.progressSink = progressRecorder
        PlaybackEnvironment.onUnauthorized = {
            sessionController.onUnauthorized("auth.device_token_invalid")
        }
        scope.launch {
            sessionController.state.collect { state ->
                PlaybackEnvironment.token = (state as? SessionState.SignedIn)?.credential?.token
                withContext(Dispatchers.Main) {
                    if (state is SessionState.SignedIn) {
                        player.connect()
                    } else {
                        player.release()
                    }
                }
            }
        }
    }
}
