package dev.trove.app.library

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import dev.trove.app.AppContainer
import dev.trove.core.download.DownloadManager
import dev.trove.core.download.DownloadPreferences
import dev.trove.core.download.DownloadSettingsStore
import dev.trove.core.library.LibraryItem
import dev.trove.core.library.LibraryRepository
import dev.trove.core.sync.SyncEngine
import dev.trove.core.sync.SyncStatus
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class LibraryUiState(
    val items: List<LibraryItem> = emptyList(),
    val allItems: List<LibraryItem> = emptyList(),
    val options: LibraryFilterOptions = LibraryFilterOptions(
        types = emptyList(),
        consumptions = emptyList(),
        tags = emptyList(),
        sources = emptyList(),
    ),
    val filters: LibraryFilters = LibraryFilters(),
    val sort: LibrarySort = LibrarySort.RECENT_ADDED,
    val syncing: Boolean = false,
    val offline: Boolean = false,
    val errorCode: String? = null,
    val lastSuccessAt: Long? = null,
    val loading: Boolean = false,
    val downloads: List<LibraryItem> = emptyList(),
    val downloadPreferences: DownloadPreferences = DownloadPreferences(),
    val continueItems: List<LibraryItem> = emptyList(),
    val conflictNotice: String? = null,
)

class LibraryViewModel(
    private val repository: LibraryRepository,
    private val syncEngine: SyncEngine,
    private val downloadManager: DownloadManager,
    private val downloadSettings: DownloadSettingsStore,
) : ViewModel() {
    private val filters = MutableStateFlow(LibraryFilters())
    private val sort = MutableStateFlow(LibrarySort.RECENT_ADDED)
    private val conflict = MutableStateFlow<String?>(null)

    val state: StateFlow<LibraryUiState> = combine(
        repository.observeLibrary(),
        syncEngine.status,
        downloadSettings.preferences,
        repository.observeDownloads(),
        combine(filters, sort, conflict) { activeFilters, activeSort, notice ->
            Triple(activeFilters, activeSort, notice)
        },
    ) { items, status, preferences, downloads, (activeFilters, activeSort, notice) ->
        LibraryUiState(
            items = applyLibraryQuery(items, activeFilters, activeSort),
            allItems = items,
            options = filterOptions(items),
            filters = activeFilters,
            sort = activeSort,
            syncing = status is SyncStatus.Syncing,
            offline = status is SyncStatus.Offline,
            errorCode = (status as? SyncStatus.Error)?.code,
            lastSuccessAt = status.lastSuccessAt,
            loading = items.isEmpty() &&
                (status is SyncStatus.Syncing ||
                    (status is SyncStatus.Idle && status.lastSuccessAt == null)),
            downloads = downloads,
            downloadPreferences = preferences,
            continueItems = items
                .filter { it.consumptionState == "in_progress" }
                .sortedByDescending { it.lastConsumedAt ?: 0L }
                .take(3),
            conflictNotice = notice,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.Eagerly,
        initialValue = LibraryUiState(),
    )

    init {
        viewModelScope.launch {
            syncEngine.conflicts.collect { conflict.value = it }
        }
    }

    fun dismissConflict() {
        conflict.value = null
    }

    fun refresh() {
        viewModelScope.launch { syncEngine.sync() }
    }

    fun setSort(value: LibrarySort) {
        sort.value = value
    }

    fun setInbox(value: Boolean) {
        filters.update { it.copy(inbox = value) }
    }

    fun setType(value: String?) {
        filters.update { it.copy(type = value) }
    }

    fun setConsumption(value: String?) {
        filters.update { it.copy(consumption = value) }
    }

    fun setTag(value: String?) {
        filters.update { it.copy(tag = value) }
    }

    fun setSource(value: String?) {
        filters.update { it.copy(source = value) }
    }

    fun clearFilters() {
        filters.value = LibraryFilters()
    }

    fun pauseDownload(itemId: String) {
        viewModelScope.launch { downloadManager.pause(itemId) }
    }

    fun retryDownload(itemId: String) {
        viewModelScope.launch { downloadManager.retry(itemId) }
    }

    fun removeDownload(itemId: String) {
        viewModelScope.launch { downloadManager.remove(itemId) }
    }

    fun setAllowMetered(value: Boolean) {
        viewModelScope.launch {
            downloadSettings.setAllowMetered(value)
            if (value) retryBlockedDownloads()
        }
    }

    fun setChargingOnly(value: Boolean) {
        viewModelScope.launch {
            downloadSettings.setChargingOnly(value)
            if (!value) retryBlockedDownloads()
        }
    }

    private suspend fun retryBlockedDownloads() {
        state.value.downloads
            .filter { it.downloadState in setOf("queued", "paused") }
            .forEach { downloadManager.retry(it.id) }
    }

    fun setQuotaBytes(value: Long) {
        viewModelScope.launch { downloadSettings.setQuotaBytes(value) }
    }

    companion object {
        fun factory(container: AppContainer): ViewModelProvider.Factory = viewModelFactory {
            initializer {
                LibraryViewModel(
                    repository = container.libraryRepository,
                    syncEngine = container.syncEngine,
                    downloadManager = container.downloadManager,
                    downloadSettings = container.downloadSettingsStore,
                )
            }
        }
    }
}
