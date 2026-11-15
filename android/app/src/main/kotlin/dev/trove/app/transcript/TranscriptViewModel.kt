package dev.trove.app.transcript

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import dev.trove.app.AppContainer
import dev.trove.core.transcript.TranscriptSegment
import dev.trove.core.library.LibraryItem
import dev.trove.core.library.LibraryRepository
import dev.trove.core.transcript.TranscriptLoadResult
import dev.trove.core.transcript.TranscriptRepository
import dev.trove.core.transcript.queryMatches
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class TranscriptUiState(
    val item: LibraryItem? = null,
    val query: String = "",
    val segments: List<TranscriptSegment> = emptyList(),
    val totalSegments: Int = 0,
    val loadResult: TranscriptLoadResult? = null,
    val loading: Boolean = false,
)

@OptIn(ExperimentalCoroutinesApi::class)
class TranscriptViewModel(
    private val repository: LibraryRepository,
    private val transcriptRepository: TranscriptRepository,
) : ViewModel() {
    private val selectedId = MutableStateFlow<String?>(null)
    private val query = MutableStateFlow("")
    private val loadResult = MutableStateFlow<TranscriptLoadResult?>(null)
    private val loading = MutableStateFlow(false)

    val state: StateFlow<TranscriptUiState> = combine(
        selectedId.flatMapLatest { id ->
            if (id == null) flowOf(null) else repository.observeItem(id)
        },
        selectedId.flatMapLatest { id ->
            if (id == null) flowOf(emptyList()) else transcriptRepository.observe(id)
        },
        query,
        loadResult,
        loading,
    ) { item, segments, activeQuery, result, isLoading ->
        TranscriptUiState(
            item = item,
            query = activeQuery,
            segments = segments.filter { queryMatches(it.text, activeQuery) },
            totalSegments = segments.size,
            loadResult = result,
            loading = isLoading,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.Eagerly,
        initialValue = TranscriptUiState(),
    )

    fun open(itemId: String) {
        if (selectedId.value == itemId) {
            load()
            return
        }
        selectedId.value = itemId
        loadResult.value = null
        query.value = ""
        load()
    }

    fun updateQuery(value: String) {
        query.value = value
    }

    fun retry() {
        load()
    }

    private fun load() {
        val itemId = selectedId.value ?: return
        loading.value = true
        viewModelScope.launch {
            loadResult.value = transcriptRepository.ensureParsed(itemId)
            loading.value = false
        }
    }

    companion object {
        fun factory(container: AppContainer): ViewModelProvider.Factory = viewModelFactory {
            initializer {
                TranscriptViewModel(
                    repository = container.libraryRepository,
                    transcriptRepository = container.transcriptRepository,
                )
            }
        }
    }
}
