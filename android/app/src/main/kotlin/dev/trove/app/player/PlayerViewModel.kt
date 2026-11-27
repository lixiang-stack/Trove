package dev.trove.app.player

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import dev.trove.app.AppContainer
import dev.trove.app.session.SessionController
import dev.trove.core.download.DownloadManager
import dev.trove.core.library.ItemMutationRepository
import dev.trove.core.library.LibraryItem
import dev.trove.core.library.LibraryRepository
import dev.trove.core.library.toUserMessage
import dev.trove.core.search.LocalSearchRepository
import dev.trove.core.settings.SettingsStore
import dev.trove.core.sync.SyncEngine
import dev.trove.core.transcript.TranscriptRepository
import dev.trove.core.transcript.TranscriptSegment
import dev.trove.playback.PlaybackRequest
import dev.trove.playback.PlaybackState
import dev.trove.playback.PlayerGateway
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.ExperimentalCoroutinesApi

private val AUTO_SYNC_STATES = setOf("none", "partial", "failed")

data class PlayerUiState(
    val itemId: String? = null,
    val item: LibraryItem? = null,
    val playback: PlaybackState = PlaybackState(),
    val loading: Boolean = false,
    val errorCode: String? = null,
    val deleted: Boolean = false,
    val transcript: List<TranscriptSegment> = emptyList(),
    val transcriptDownloaded: Boolean = false,
    val tagError: String? = null,
)

@OptIn(ExperimentalCoroutinesApi::class)
class PlayerViewModel(
    private val repository: LibraryRepository,
    private val player: PlayerGateway,
    private val downloadManager: DownloadManager,
    private val settingsStore: SettingsStore,
    private val transcriptRepository: TranscriptRepository,
    private val sessionController: SessionController,
    private val itemMutationRepository: ItemMutationRepository,
    private val localSearchRepository: LocalSearchRepository,
    private val syncEngine: SyncEngine,
) : ViewModel() {
    private val selectedId = MutableStateFlow<String?>(null)
    private val errorCode = MutableStateFlow<String?>(null)
    private val deleted = MutableStateFlow(false)
    private val tagError = MutableStateFlow<String?>(null)
    private var hasLoadedItem = false
    private val autoSyncMutex = Mutex()

    val state: StateFlow<PlayerUiState> = combine(
        selectedId,
        selectedId.flatMapLatest { id ->
            if (id == null) flowOf(null) else repository.observeItem(id)
        },
        player.state,
        selectedId.flatMapLatest { id ->
            if (id == null) flowOf(emptyList()) else transcriptRepository.observe(id)
        },
        combine(errorCode, deleted, tagError) { error, isDeleted, tagFailure ->
            Triple(error, isDeleted, tagFailure)
        },
    ) { id, item, playback, transcript, (error, isDeleted, tagFailure) ->
        PlayerUiState(
            itemId = id,
            item = item,
            playback = playback,
            loading = id != null && item == null && !isDeleted,
            errorCode = error,
            deleted = isDeleted,
            transcript = transcript,
            transcriptDownloaded = item?.transcriptArtifact?.downloadState == "completed",
            tagError = tagFailure,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.Eagerly,
        initialValue = PlayerUiState(),
    )

    init {
        viewModelScope.launch {
            selectedId
                .flatMapLatest { id ->
                    if (id == null) flowOf(null) else repository.observeItem(id)
                }
                .collect { item ->
                    if (item != null) {
                        hasLoadedItem = true
                    } else if (selectedId.value != null && hasLoadedItem) {
                        deleted.value = true
                    }
                }
        }
        viewModelScope.launch {
            player.state
                .map { it.itemId to it.ended }
                .distinctUntilChanged()
                .collect { (itemId, ended) ->
                    repository.cleanupPendingFiles(if (ended) null else itemId)
                }
        }
    }

    fun open(itemId: String, autoPlay: Boolean) {
        selectedId.value = itemId
        errorCode.value = null
        deleted.value = false
        hasLoadedItem = false
        autoSync(itemId)
        if (!autoPlay) {
            val current = player.state.value
            if (current.itemId != null && current.itemId != itemId) {
                player.pause()
            }
            return
        }
        viewModelScope.launch {
            val item = repository.find(itemId)
            if (item == null) {
                errorCode.value = "item.missing"
                return@launch
            }
            val current = player.state.value
            if (current.itemId == item.id) {
                if (!current.isPlaying) player.toggle()
            } else {
                playItem(item)
            }
        }
    }

    fun toggle() {
        val current = state.value
        val item = current.item ?: return
        when {
            current.playback.errorCode != null -> viewModelScope.launch { playItem(item) }
            current.playback.itemId == item.id -> player.toggle()
            else -> viewModelScope.launch { playItem(item) }
        }
    }

    fun retry() {
        val item = state.value.item ?: return
        errorCode.value = null
        viewModelScope.launch { playItem(item) }
    }

    fun seekTo(positionMs: Long) {
        player.seekTo(positionMs)
    }

    fun seekBy(deltaMs: Long) {
        val playback = player.state.value
        val target = playback.positionMs + deltaMs
        val upper = if (playback.durationMs > 0) playback.durationMs else Long.MAX_VALUE
        player.seekTo(target.coerceIn(0, upper))
    }

    fun setSpeed(speed: Float) {
        player.setSpeed(speed)
    }

    fun download() {
        val itemId = selectedId.value ?: return
        viewModelScope.launch { downloadManager.enqueue(itemId) }
    }

    fun removeDownload() {
        val itemId = selectedId.value ?: return
        viewModelScope.launch { downloadManager.remove(itemId) }
    }

    fun pauseDownload() {
        val itemId = selectedId.value ?: return
        viewModelScope.launch { downloadManager.pause(itemId) }
    }

    fun retryDownload() {
        val itemId = selectedId.value ?: return
        viewModelScope.launch { downloadManager.retry(itemId) }
    }

    fun deleteItem() {
        val itemId = selectedId.value ?: return
        viewModelScope.launch {
            val client = sessionController.currentClient()
                ?: run {
                    errorCode.value = "auth.required"
                    return@launch
                }
            try {
                client.deleteItem(itemId)
                player.pause()
                repository.deleteLocalItem(itemId)
                runCatching { localSearchRepository.removeItem(itemId) }
                deleted.value = true
            } catch (_: Exception) {
                errorCode.value = "item.delete_failed"
            }
        }
    }

    fun replaceTags(tags: List<String>) {
        val itemId = selectedId.value ?: return
        viewModelScope.launch {
            runCatching { itemMutationRepository.replaceTags(itemId, tags) }
                .onSuccess { tagError.value = null }
                .onFailure { error ->
                    tagError.value = when (error) {
                        is dev.trove.core.tags.InvalidTagException -> error.toUserMessage()
                        else -> "标签保存失败，请重试。"
                    }
                }
        }
    }

    fun clearTagError() {
        tagError.value = null
    }

    fun retryProcessing() {
        val itemId = selectedId.value ?: return
        viewModelScope.launch {
            val client = sessionController.currentClient()
            if (client == null) {
                errorCode.value = "auth.required"
                return@launch
            }
            runCatching {
                client.retryItem(itemId)
                syncEngine.sync()
            }.onFailure {
                errorCode.value = "item.retry_failed"
            }
        }
    }

    fun setConsumption(state: String) {
        val itemId = selectedId.value ?: return
        viewModelScope.launch { itemMutationRepository.setConsumption(itemId, state) }
    }

    fun refreshTranscript() {
        val itemId = selectedId.value ?: return
        viewModelScope.launch {
            try {
                transcriptRepository.ensureParsed(itemId)
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                // Transcript load failures surface through the transcript state.
            }
        }
    }

    private fun autoSync(itemId: String) {
        viewModelScope.launch {
            autoSyncMutex.withLock {
                val item = repository.find(itemId) ?: return@withLock
                if (item.artifacts.isEmpty()) return@withLock
                if (item.downloadState == "queued") {
                    downloadManager.resumePending()
                    return@withLock
                }
                if (item.downloadState !in AUTO_SYNC_STATES) {
                    return@withLock
                }
                downloadManager.enqueue(itemId)
            }
        }
    }

    private suspend fun playItem(item: LibraryItem) {
        val audio = item.audioArtifact
        if (audio == null) {
            errorCode.value = "playback.no_audio"
            return
        }
        val local = fileIfPresent(audio.localPath)
        val url = local?.toURI()?.toString() ?: run {
            val host = settingsStore.hostUrl.first()
            if (host.isNullOrBlank()) {
                errorCode.value = "playback.offline"
                return
            }
            "${host.trimEnd('/')}/api/items/${item.id}/files/audio"
        }
        val artwork = fileIfPresent(item.coverArtifact?.localPath)?.toURI()?.toString()
        val start = player.state.value.let { current ->
            if (current.itemId == item.id) current.positionMs
            else (item.audioPositionSec * 1000).toLong()
        }
        player.play(
            PlaybackRequest(
                itemId = item.id,
                url = url,
                title = item.title,
                artist = item.author,
                artworkUrl = artwork,
                startPositionMs = start.coerceAtLeast(0),
            )
        )
    }

    private fun fileIfPresent(path: String?): File? =
        path?.let(::File)?.takeIf { it.isFile }

    companion object {
        fun factory(container: AppContainer): ViewModelProvider.Factory = viewModelFactory {
            initializer {
                PlayerViewModel(
                    repository = container.libraryRepository,
                    player = container.player,
                    downloadManager = container.downloadManager,
                    settingsStore = container.settingsStore,
                    transcriptRepository = container.transcriptRepository,
                    sessionController = container.sessionController,
                    itemMutationRepository = container.itemMutationRepository,
                    localSearchRepository = container.localSearchRepository,
                    syncEngine = container.syncEngine,
                )
            }
        }
    }
}
