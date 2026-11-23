package dev.trove.app.library

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import dev.trove.app.AppContainer
import dev.trove.app.session.SessionController
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
    val entries: List<LibraryEntry> = emptyList(),
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
    val queuedDownloads: Int = 0,
    val conflictNotice: String? = null,
    val collectionActionError: String? = null,
)

private data class LibraryActionState(
    val filters: LibraryFilters,
    val sort: LibrarySort,
    val conflictNotice: String?,
    val collectionActionError: String?,
)

class LibraryViewModel(
    private val repository: LibraryRepository,
    private val syncEngine: SyncEngine,
    private val downloadManager: DownloadManager,
    private val downloadSettings: DownloadSettingsStore,
    private val sessionController: SessionController,
) : ViewModel() {
    private val filters = MutableStateFlow(LibraryFilters())
    private val sort = MutableStateFlow(LibrarySort.RECENT_ADDED)
    private val conflict = MutableStateFlow<String?>(null)
    private val collectionActionError = MutableStateFlow<String?>(null)

    val state: StateFlow<LibraryUiState> = combine(
        repository.observeLibrary(),
        syncEngine.status,
        downloadSettings.preferences,
        repository.observeDownloads(),
        combine(filters, sort, conflict, collectionActionError) {
                activeFilters, activeSort, notice, actionError ->
            LibraryActionState(activeFilters, activeSort, notice, actionError)
        },
    ) { items, status, preferences, downloads, action ->
        LibraryUiState(
            items = applyLibraryQuery(items, action.filters, action.sort),
            entries = applyLibraryEntryQuery(
                items.toLibraryEntries(),
                action.filters,
                action.sort,
            ),
            allItems = items,
            options = filterOptions(items),
            filters = action.filters,
            sort = action.sort,
            syncing = status is SyncStatus.Syncing,
            offline = status is SyncStatus.Offline,
            errorCode = (status as? SyncStatus.Error)?.code,
            lastSuccessAt = status.lastSuccessAt,
            loading = items.isEmpty() &&
                (status is SyncStatus.Syncing ||
                    (status is SyncStatus.Idle && status.lastSuccessAt == null)),
            downloads = downloads,
            downloadPreferences = preferences,
            queuedDownloads = downloads.count { it.downloadState == "queued" },
            conflictNotice = action.conflictNotice,
            collectionActionError = action.collectionActionError,
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

    fun clearCollectionActionError() {
        collectionActionError.value = null
    }

    fun deleteCollection(collectionId: String, mode: String) {
        val client = sessionController.currentClient() ?: return
        viewModelScope.launch {
            try {
                client.deleteCollection(collectionId, mode)
                syncEngine.sync()
            } catch (error: Exception) {
                collectionActionError.value = error.message ?: "删除合集失败"
            }
        }
    }

    fun downloadCollection(collectionId: String) {
        viewModelScope.launch {
            val itemIds = state.value.allItems
                .filter { it.collectionId == collectionId && it.artifacts.isNotEmpty() }
                .map { it.id }
            if (itemIds.isNotEmpty()) downloadManager.enqueueAll(itemIds)
        }
    }

    fun retryCollectionItem(itemId: String) {
        val client = sessionController.currentClient() ?: return
        viewModelScope.launch {
            try {
                client.retryItem(itemId)
                syncEngine.sync()
            } catch (error: Exception) {
                collectionActionError.value = error.message ?: "重试失败"
            }
        }
    }

    fun retryCollectionFailed(collectionId: String) {
        val client = sessionController.currentClient() ?: return
        viewModelScope.launch {
            try {
                client.retryCollectionFailed(collectionId)
                syncEngine.sync()
            } catch (error: Exception) {
                collectionActionError.value = error.message ?: "重试失败"
            }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            syncEngine.sync()
            downloadManager.resumePending()
        }
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
                    sessionController = container.sessionController,
                )
            }
        }
    }
}
