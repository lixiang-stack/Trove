package dev.trove.app.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import dev.trove.app.AppContainer
import dev.trove.app.session.SessionController
import dev.trove.app.session.SessionState
import dev.trove.core.download.DownloadPreferences
import dev.trove.core.download.DownloadSettingsStore
import dev.trove.core.settings.MIN_SYNC_INTERVAL_MINUTES
import dev.trove.core.settings.SettingsStore
import dev.trove.core.settings.SyncPreferences
import dev.trove.core.search.LocalSearchRepository
import dev.trove.core.storage.LocalDataRepository
import dev.trove.core.sync.SyncEngine
import dev.trove.core.sync.SyncStatus
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SettingsStorage(
    val downloadedBytes: Long = 0,
    val quotaBytes: Long = 0,
    val availableBytes: Long = 0,
    val downloadQueue: Int = 0,
    val contentCursor: String? = null,
    val stateCursor: String? = null,
    val epoch: String? = null,
)

data class SettingsDiagnostics(
    val apiVersion: String = "未知",
    val capabilities: List<String> = emptyList(),
    val errorCode: String? = null,
    val pendingMutations: Int = 0,
    val pendingErrorCode: String? = null,
)

private data class SettingsExtras(
    val storage: SettingsStorage = SettingsStorage(),
    val diagnostics: SettingsDiagnostics = SettingsDiagnostics(),
    val message: String? = null,
    val clearing: Boolean = false,
)

data class SettingsUiState(
    val hostUrl: String = "",
    val deviceName: String = "",
    val deviceId: String = "",
    val syncPreferences: SyncPreferences = SyncPreferences(),
    val downloadPreferences: DownloadPreferences = DownloadPreferences(),
    val syncing: Boolean = false,
    val offline: Boolean = false,
    val syncErrorCode: String? = null,
    val lastSuccessAt: Long? = null,
    val storage: SettingsStorage = SettingsStorage(),
    val diagnostics: SettingsDiagnostics = SettingsDiagnostics(),
    val message: String? = null,
    val clearing: Boolean = false,
)

class SettingsViewModel(
    private val settingsStore: SettingsStore,
    private val downloadSettings: DownloadSettingsStore,
    private val syncEngine: SyncEngine,
    private val sessionController: SessionController,
    private val localData: LocalDataRepository,
    private val localSearch: LocalSearchRepository,
) : ViewModel() {
    private val extras = MutableStateFlow(SettingsExtras())

    val state: StateFlow<SettingsUiState> = combine(
        sessionController.state,
        settingsStore.syncPreferences,
        downloadSettings.preferences,
        syncEngine.status,
        extras,
    ) { session, syncPreferences, downloadPreferences, status, extra ->
        val signedIn = session as? SessionState.SignedIn
        SettingsUiState(
            hostUrl = signedIn?.hostUrl.orEmpty(),
            deviceName = signedIn?.credential?.deviceName.orEmpty(),
            deviceId = signedIn?.credential?.deviceId.orEmpty(),
            syncPreferences = syncPreferences,
            downloadPreferences = downloadPreferences,
            syncing = status is SyncStatus.Syncing,
            offline = status is SyncStatus.Offline,
            syncErrorCode = (status as? SyncStatus.Error)?.code
                ?: extra.diagnostics.errorCode,
            lastSuccessAt = status.lastSuccessAt,
            storage = extra.storage,
            diagnostics = extra.diagnostics,
            message = extra.message,
            clearing = extra.clearing,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.Eagerly,
        initialValue = SettingsUiState(),
    )

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            val cursor = syncEngine.currentCursor()
            val preferences = downloadSettings.preferences.first()
            val storage = SettingsStorage(
                downloadedBytes = localData.downloadedBytes(),
                quotaBytes = preferences.quotaBytes,
                availableBytes = localData.availableBytes(),
                downloadQueue = localData.downloadQueueSize(),
                contentCursor = cursor?.contentCursor,
                stateCursor = cursor?.stateCursor,
                epoch = cursor?.epoch,
            )
            extras.update { it.copy(storage = storage) }
            val pendingMutations = syncEngine.pendingMutationCount()
            val pendingError = syncEngine.lastPendingError()
            val health = sessionController.health()
            extras.update {
                it.copy(
                    diagnostics = SettingsDiagnostics(
                        apiVersion = health?.apiVersion ?: "未知",
                        capabilities = health?.capabilities
                            ?.filterValues { enabled -> enabled }
                            ?.keys
                            ?.sorted()
                            .orEmpty(),
                        errorCode = cursor?.errorCode,
                        pendingMutations = pendingMutations,
                        pendingErrorCode = pendingError,
                    )
                )
            }
        }
    }

    fun syncNow() {
        viewModelScope.launch {
            syncEngine.sync()
            refresh()
        }
    }

    fun setPeriodicEnabled(value: Boolean) {
        viewModelScope.launch { settingsStore.setPeriodicSyncEnabled(value) }
    }

    fun setIntervalMinutes(value: Long) {
        val interval = value.coerceAtLeast(MIN_SYNC_INTERVAL_MINUTES)
        viewModelScope.launch { settingsStore.setSyncIntervalMinutes(interval) }
    }

    fun setAllowMetered(value: Boolean) {
        viewModelScope.launch {
            downloadSettings.setAllowMetered(value)
            refresh()
        }
    }

    fun setChargingOnly(value: Boolean) {
        viewModelScope.launch { downloadSettings.setChargingOnly(value) }
    }

    fun setQuotaBytes(value: Long) {
        viewModelScope.launch {
            downloadSettings.setQuotaBytes(value)
            extras.update { it.copy(storage = it.storage.copy(quotaBytes = value)) }
        }
    }

    fun signOut() {
        viewModelScope.launch { sessionController.logout() }
    }

    fun clearLocalData() {
        viewModelScope.launch {
            extras.update { it.copy(clearing = true, message = null) }
            runCatching { localData.clearAll() }
                .onSuccess {
                    extras.update {
                        it.copy(clearing = false, message = "本地数据已清除；下载和同步游标已重置。")
                    }
                    refresh()
                }
                .onFailure {
                    extras.update { it.copy(clearing = false, message = "清除失败，请重试。") }
                }
        }
    }

    fun dismissMessage() {
        extras.update { it.copy(message = null) }
    }

    fun rebuildSearchIndex() {
        viewModelScope.launch {
            extras.update { it.copy(message = "正在重建搜索索引…") }
            runCatching { localSearch.rebuild() }
                .onSuccess {
                    extras.update { it.copy(message = "搜索索引已重建。") }
                }
                .onFailure {
                    extras.update { it.copy(message = "搜索索引重建失败。") }
                }
        }
    }

    companion object {
        fun factory(container: AppContainer): ViewModelProvider.Factory = viewModelFactory {
            initializer {
                SettingsViewModel(
                    settingsStore = container.settingsStore,
                    downloadSettings = container.downloadSettingsStore,
                    syncEngine = container.syncEngine,
                    sessionController = container.sessionController,
                    localData = container.localDataRepository,
                    localSearch = container.localSearchRepository,
                )
            }
        }
    }
}
