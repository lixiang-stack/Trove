package dev.trove.app.search

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import dev.trove.app.AppContainer
import dev.trove.core.network.TroveApiException
import dev.trove.core.network.TroveClient
import dev.trove.core.network.TroveNetworkException
import dev.trove.core.network.TroveTlsException
import dev.trove.core.search.LocalSearchRepository
import dev.trove.core.search.LocalSearchUnavailableException
import dev.trove.core.search.MAX_QUERY_LENGTH
import dev.trove.core.search.SearchFilters
import dev.trove.core.search.SearchQueryTooLongException
import dev.trove.core.sync.SyncEngine
import dev.trove.core.sync.SyncStatus
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SearchUiState(
    val query: String = "",
    val filters: SearchFilters = SearchFilters(),
    val results: List<SearchUiResult> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
    val offline: Boolean = false,
    val localOnly: Boolean = false,
    val hasSearched: Boolean = false,
)

class SearchViewModel(
    private val localSearch: LocalSearchRepository,
    private val syncEngine: SyncEngine,
    private val session: () -> TroveClient?,
) : ViewModel() {
    private val _state = MutableStateFlow(SearchUiState())
    val state: StateFlow<SearchUiState> = _state.asStateFlow()
    private var searchJob: Job? = null
    private var pending: Job? = null

    init {
        viewModelScope.launch {
            syncEngine.status.collect { status ->
                _state.update { it.copy(offline = status is SyncStatus.Offline) }
            }
        }
    }

    fun updateQuery(value: String) {
        _state.update { it.copy(query = value) }
        schedule()
    }

    fun setFilters(filters: SearchFilters) {
        _state.update { it.copy(filters = filters) }
        if (_state.value.query.isNotBlank()) search()
    }

    fun clearFilters() {
        setFilters(SearchFilters())
    }

    fun retry() {
        search()
    }

    private fun schedule() {
        pending?.cancel()
        pending = viewModelScope.launch {
            delay(300)
            search()
        }
    }

    private fun search() {
        val query = _state.value.query.trim()
        if (query.isEmpty()) {
            searchJob?.cancel()
            _state.update {
                it.copy(results = emptyList(), loading = false, error = null, hasSearched = false)
            }
            return
        }
        if (query.length > MAX_QUERY_LENGTH) {
            _state.update {
                it.copy(
                    results = emptyList(),
                    loading = false,
                    hasSearched = true,
                    error = "搜索词过长，最多 200 个字符。",
                )
            }
            return
        }
        searchJob?.cancel()
        searchJob = viewModelScope.launch {
            _state.update {
                it.copy(loading = true, error = null, hasSearched = true)
            }
            val filters = _state.value.filters
            val results = try {
                if (_state.value.offline) {
                    local(query, filters, localOnly = true)
                } else {
                    val client = session()
                    if (client == null) {
                        local(query, filters, localOnly = true)
                    } else {
                        val response = client.search(
                            query = query,
                            type = filters.type,
                            consumption = filters.consumption,
                            tag = filters.tag,
                            source = filters.source,
                            limit = 50,
                        )
                        _state.update { it.copy(localOnly = false) }
                        response.results.map { it.toUiResult() }
                    }
                }
            } catch (_: TroveNetworkException) {
                local(query, filters, localOnly = true)
            } catch (_: TroveTlsException) {
                local(query, filters, localOnly = true)
            } catch (error: TroveApiException) {
                if (error.statusCode == 401) {
                    _state.update { it.copy(loading = false, error = "登录已失效，请重新登录。") }
                    return@launch
                }
                local(query, filters, localOnly = true)
            } catch (_: SearchQueryTooLongException) {
                _state.update { it.copy(loading = false, error = "搜索词过长，最多 200 个字符。") }
                return@launch
            } catch (_: LocalSearchUnavailableException) {
                _state.update {
                    it.copy(
                        loading = false,
                        results = emptyList(),
                        localOnly = true,
                        error = "本地搜索索引不可用；播放和阅读仍可使用。",
                    )
                }
                return@launch
            } catch (error: Exception) {
                android.util.Log.e("TroveSearch", "local search failed", error)
                _state.update {
                    it.copy(
                        loading = false,
                        results = emptyList(),
                        error = "搜索失败，请重试。",
                    )
                }
                return@launch
            }
            _state.update { it.copy(loading = false, results = results, error = null) }
        }
    }

    private suspend fun local(
        query: String,
        filters: SearchFilters,
        localOnly: Boolean,
    ): List<SearchUiResult> {
        if (!localSearch.isAvailable()) throw LocalSearchUnavailableException()
        val results = localSearch.search(query, filters).map { it.toUiResult() }
        _state.update { it.copy(localOnly = localOnly) }
        return results
    }

    companion object {
        fun factory(container: AppContainer): ViewModelProvider.Factory = viewModelFactory {
            initializer {
                SearchViewModel(
                    localSearch = container.localSearchRepository,
                    syncEngine = container.syncEngine,
                    session = { container.sessionController.currentClient() },
                )
            }
        }
    }
}
