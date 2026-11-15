package dev.trove.app.add

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import dev.trove.app.AppContainer
import dev.trove.core.network.FeedEpisodeDto
import dev.trove.core.network.FeedPreviewResponseDto
import dev.trove.core.network.ItemCreateRequestDto
import dev.trove.core.network.ItemDto
import dev.trove.core.network.TroveApiException
import dev.trove.core.network.TroveClient
import dev.trove.core.network.TroveNetworkException
import dev.trove.core.network.TroveTlsException
import dev.trove.app.session.SessionController
import dev.trove.core.sync.SyncEngine
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AddUiState(
    val url: String = "",
    val feedUrl: String = "",
    val submitting: Boolean = false,
    val previewing: Boolean = false,
    val error: String? = null,
    val preview: FeedPreviewResponseDto? = null,
    val created: ItemDto? = null,
    val deduplicated: Boolean = false,
)

class AddViewModel(
    private val sessionController: SessionController,
    private val syncEngine: SyncEngine,
) : ViewModel() {
    private val _state = MutableStateFlow(AddUiState())
    val state: StateFlow<AddUiState> = _state.asStateFlow()
    private var pollJob: Job? = null

    fun updateUrl(value: String) {
        _state.update { it.copy(url = value, error = null) }
    }

    fun updateFeed(value: String) {
        _state.update { it.copy(feedUrl = value, error = null) }
    }

    fun prefill(url: String) {
        _state.update { it.copy(url = url, error = null) }
    }

    fun submitUrl() {
        val url = _state.value.url.trim()
        if (url.isEmpty()) {
            _state.update { it.copy(error = "请输入 URL") }
            return
        }
        submit(ItemCreateRequestDto(kind = "url", url = url))
    }

    fun previewFeed() {
        val url = _state.value.feedUrl.trim()
        if (url.isEmpty()) {
            _state.update { it.copy(error = "请输入播客 feed URL") }
            return
        }
        val client = sessionController.currentClient()
        if (client == null) {
            _state.update { it.copy(error = "登录已失效，请重新登录。") }
            return
        }
        _state.update { it.copy(previewing = true, error = null) }
        viewModelScope.launch {
            try {
                val preview = client.previewFeed(url)
                _state.update { it.copy(previewing = false, preview = preview) }
            } catch (error: Exception) {
                _state.update {
                    it.copy(previewing = false, error = addErrorLabel(error))
                }
            }
        }
    }

    fun addEpisode(episode: FeedEpisodeDto) {
        val feedUrl = _state.value.feedUrl.trim()
        submit(
            ItemCreateRequestDto(
                kind = "podcast",
                feedUrl = feedUrl,
                episodeGuid = episode.guid,
                enclosureUrl = episode.enclosureUrl,
            )
        )
    }

    fun retry() {
        val item = _state.value.created ?: return
        val client = sessionController.currentClient() ?: return
        viewModelScope.launch {
            try {
                val updated = client.retryItem(item.id)
                _state.update { it.copy(created = updated, error = null) }
                syncEngine.sync()
                poll(item.id)
            } catch (error: Exception) {
                _state.update { it.copy(error = addErrorLabel(error)) }
            }
        }
    }

    fun consumeDeduplicated() {
        _state.update { it.copy(deduplicated = false) }
    }

    private fun submit(request: ItemCreateRequestDto) {
        val client = sessionController.currentClient()
        if (client == null) {
            _state.update { it.copy(error = "登录已失效，请重新登录。") }
            return
        }
        _state.update { it.copy(submitting = true, error = null, created = null, deduplicated = false) }
        viewModelScope.launch {
            try {
                val response = client.createItem(request)
                _state.update {
                    it.copy(
                        submitting = false,
                        created = response.item,
                        deduplicated = response.deduplicated,
                    )
                }
                syncEngine.sync()
                poll(response.item.id)
            } catch (error: Exception) {
                _state.update { it.copy(submitting = false, error = addErrorLabel(error)) }
            }
        }
    }

    private fun poll(itemId: String) {
        pollJob?.cancel()
        pollJob = viewModelScope.launch {
            var attempts = 0
            while (attempts < MAX_POLLS) {
                attempts += 1
                delay(pollDelay(attempts))
                val client = sessionController.currentClient() ?: return@launch
                val item = try {
                    client.item(itemId)
                } catch (_: Exception) {
                    continue
                }
                _state.update { it.copy(created = item) }
                if (item.processingState in TERMINAL_STATES) {
                    syncEngine.sync()
                    return@launch
                }
            }
        }
    }

    private fun pollDelay(attempt: Int): Long =
        if (attempt < 10) 2_000 else 5_000

    private fun addErrorLabel(error: Exception): String = when (error) {
        is TroveNetworkException -> "无法连接 Host，请检查网络。"
        is TroveTlsException -> "TLS 证书不受信任，请检查 Host 配置。"
        is TroveApiException -> when (error.code) {
            "url.empty" -> "请输入 URL。"
            "url.scheme" -> "只支持 http/https URL。"
            "url.credentials" -> "URL 不能包含账号或密码。"
            "url.unsupported_platform" -> "不支持这个平台。"
            "url.unsupported_type" -> "不支持这种链接类型。"
            "url.live_not_supported" -> "暂不支持直播链接。"
            "url.playlist_not_supported" -> "暂不支持播放列表或多 P 链接，请粘贴单条视频。"
            "url.parse" -> "无法识别这个链接。"
            "feed.scheme", "feed.parse" -> "播客 feed 地址无效。"
            "feed.credentials" -> "播客 feed 地址不能包含账号或密码。"
            "feed.episode_not_found" -> "没有在 feed 中找到这一集。"
            "auth.required", "auth.device_revoked" -> "登录已失效，请重新登录。"
            else -> error.message.ifBlank { "请求失败，请稍后重试。" }
        }
        else -> "请求失败，请稍后重试。"
    }

    companion object {
        private const val MAX_POLLS = 60
        private val TERMINAL_STATES = setOf("completed", "failed", "cancelled")

        fun factory(container: AppContainer): ViewModelProvider.Factory = viewModelFactory {
            initializer {
                AddViewModel(
                    sessionController = container.sessionController,
                    syncEngine = container.syncEngine,
                )
            }
        }
    }
}
