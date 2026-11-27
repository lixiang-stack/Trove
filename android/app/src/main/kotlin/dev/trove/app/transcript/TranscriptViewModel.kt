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
import kotlinx.coroutines.CancellationException
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
    val focusSeq: Int? = null,
)

private data class TranscriptTarget(val itemId: String, val focusSeq: Int? = null)

@OptIn(ExperimentalCoroutinesApi::class)
class TranscriptViewModel(
    private val repository: LibraryRepository,
    private val transcriptRepository: TranscriptRepository,
) : ViewModel() {
    private val target = MutableStateFlow<TranscriptTarget?>(null)
    private val query = MutableStateFlow("")
    private val loadResult = MutableStateFlow<TranscriptLoadResult?>(null)
    private val loading = MutableStateFlow(false)

    val state: StateFlow<TranscriptUiState> = combine(
        target.flatMapLatest { value ->
            if (value == null) flowOf(null) else repository.observeItem(value.itemId)
        },
        target.flatMapLatest { value ->
            if (value == null) flowOf(emptyList()) else transcriptRepository.observe(value.itemId)
        },
        combine(query, target) { activeQuery, value -> activeQuery to value?.focusSeq },
        loadResult,
        loading,
    ) { item, segments, (activeQuery, focusSeq), result, isLoading ->
        TranscriptUiState(
            item = item,
            query = activeQuery,
            segments = segments.filter { queryMatches(it.text, activeQuery) },
            totalSegments = segments.size,
            loadResult = result,
            loading = isLoading,
            focusSeq = focusSeq,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.Eagerly,
        initialValue = TranscriptUiState(),
    )

    fun open(itemId: String, focusSeq: Int? = null, initialQuery: String = "") {
        val changed = target.value?.itemId != itemId
        target.value = TranscriptTarget(itemId, focusSeq)
        query.value = initialQuery
        if (changed) loadResult.value = null
        load()
    }

    fun updateQuery(value: String) {
        query.value = value
    }

    fun retry() {
        load()
    }

    private fun load() {
        val itemId = target.value?.itemId ?: return
        loading.value = true
        viewModelScope.launch {
            loadResult.value = try {
                transcriptRepository.ensureParsed(itemId)
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                TranscriptLoadResult.Failed
            }
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
