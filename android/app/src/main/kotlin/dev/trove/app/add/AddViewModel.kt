package dev.trove.app.add

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import dev.trove.app.AppContainer
import dev.trove.app.session.SessionController
import dev.trove.core.network.CollectionCreateResponseDto
import dev.trove.core.network.FeedEpisodeDto
import dev.trove.core.network.ItemCreateRequestDto
import dev.trove.core.network.ItemDto
import dev.trove.core.network.LinkInspectResponseDto
import dev.trove.core.network.TroveApiException
import dev.trove.core.network.TroveClient
import dev.trove.core.network.TroveNetworkException
import dev.trove.core.network.TroveTlsException
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
    val detecting: Boolean = false,
    val submitting: Boolean = false,
    val error: String? = null,
    val inspection: LinkInspectResponseDto? = null,
    val created: ItemDto? = null,
    val createdCollection: CollectionCreateResponseDto? = null,
    val deduplicated: Boolean = false,
)

class AddViewModel(
    private val sessionController: SessionController,
    private val syncEngine: SyncEngine,
) : ViewModel() {
    private val _state = MutableStateFlow(AddUiState())
    val state: StateFlow<AddUiState> = _state.asStateFlow()
    private var pollJob: Job? = null
    private var detectJob: Job? = null

    fun updateUrl(value: String) {
        detectJob?.cancel()
        _state.update {
            it.copy(
                url = value,
                error = null,
                inspection = null,
                created = null,
                createdCollection = null,
                deduplicated = false,
            )
        }
        if (value.isBlank()) return
        detectJob = viewModelScope.launch {
            delay(600)
            detect(showError = false)
        }
    }

    fun prefill(url: String) {
        updateUrl(url)
    }

    fun detectNow() {
        if (_state.value.url.isBlank()) {
            _state.update { it.copy(error = "请输入链接") }
            return
        }
        detectJob?.cancel()
        _state.update { it.copy(inspection = null, created = null, createdCollection = null) }
        viewModelScope.launch { detect(showError = true) }
    }

    fun submit() {
        val state = _state.value
        if (state.url.isBlank()) {
            _state.update { it.copy(error = "请输入链接") }
            return
        }
        if (state.inspection == null) {
            detectJob?.cancel()
            viewModelScope.launch { detect(showError = true) }
            return
        }
        val inspection = state.inspection
        when (inspection.kind) {
            "video" -> submitItem(
                ItemCreateRequestDto(kind = "url", url = inspection.canonicalUrl)
            )
            "ebook" -> submitItem(ItemCreateRequestDto(kind = "ebook_url", url = state.url))
            "collection" -> submitCollection(state.url)
            "podcast_feed" -> _state.update {
                it.copy(error = "请选择一集播客入库。")
            }
            else -> _state.update { it.copy(error = "不支持这个链接。") }
        }
    }

    fun addEpisode(episode: FeedEpisodeDto) {
        val state = _state.value
        val feedUrl = state.inspection?.canonicalUrl ?: state.url
        submitItem(
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

    fun clearResult() {
        _state.update {
            it.copy(
                url = "",
                inspection = null,
                created = null,
                createdCollection = null,
                deduplicated = false,
                error = null,
            )
        }
    }

    private suspend fun detect(showError: Boolean) {
        val url = _state.value.url.trim()
        if (url.isEmpty()) return
        val client = sessionController.currentClient()
        if (client == null) {
            _state.update { it.copy(error = "登录已失效，请重新登录。") }
            return
        }
        _state.update { it.copy(detecting = true, error = null) }
        try {
            val inspection = client.inspectLink(url)
            _state.update {
                it.copy(
                    detecting = false,
                    inspection = inspection,
                    created = null,
                    createdCollection = null,
                )
            }
        } catch (error: Exception) {
            _state.update {
                it.copy(
                    detecting = false,
                    error = if (showError) addErrorLabel(error) else null,
                )
            }
        }
    }

    private fun submitCollection(url: String) {
        val client = sessionController.currentClient()
        if (client == null) {
            _state.update { it.copy(error = "登录已失效，请重新登录。") }
            return
        }
        _state.update {
            it.copy(
                submitting = true,
                error = null,
                created = null,
                createdCollection = null,
            )
        }
        viewModelScope.launch {
            try {
                val response = client.createCollection(url)
                _state.update {
                    it.copy(submitting = false, createdCollection = response)
                }
                syncEngine.sync()
            } catch (error: Exception) {
                _state.update { it.copy(submitting = false, error = addErrorLabel(error)) }
            }
        }
    }

    private fun submitItem(request: ItemCreateRequestDto) {
        val client = sessionController.currentClient()
        if (client == null) {
            _state.update { it.copy(error = "登录已失效，请重新登录。") }
            return
        }
        _state.update {
            it.copy(
                submitting = true,
                error = null,
                created = null,
                createdCollection = null,
                deduplicated = false,
            )
        }
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
                if (!response.deduplicated) poll(response.item.id)
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
        is TroveApiException -> API_ERROR_LABELS[error.code]
            ?: error.message.ifBlank { "请求失败，请稍后重试。" }
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

private val API_ERROR_LABELS = mapOf(
    "url.empty" to "请输入链接。",
    "link.empty" to "请输入链接。",
    "url.scheme" to "只支持 http/https 链接。",
    "link.scheme" to "只支持 http/https 链接。",
    "url.credentials" to "链接不能包含账号或密码。",
    "link.credentials" to "链接不能包含账号或密码。",
    "url.unsupported_platform" to "不支持这个平台。",
    "link.unsupported" to "不支持这个链接。请粘贴 B 站/YouTube 单集或合集、EPUB 直链、播客 feed。",
    "url.unsupported_type" to "不支持这种链接类型。",
    "url.live_not_supported" to "暂不支持直播链接。",
    "link.live_not_supported" to "暂不支持直播链接。",
    "url.parse" to "无法识别这个链接。",
    "inspect.timeout" to "识别超时，请重试。",
    "inspect.failed" to "识别链接失败，请重试。",
    "download.login_required" to "这个链接需要登录或 Cookie 才能读取。",
    "download.geo_restricted" to "这个内容在你所在地区不可用。",
    "download.parse" to "无法解析链接内容。",
    "collection.too_large" to "合集超出 100 集或 100 小时上限。",
    "collection.empty" to "这个链接没有可入库的合集单集。",
    "collection.not_found" to "合集不存在或已删除。",
    "collection.episode_invalid" to "合集里有无法识别的单集。",
    "ebook.invalid_type" to "这个链接不是 EPUB 文件。",
    "ebook.too_large" to "EPUB 超过 100 MB 上限。",
    "ebook.not_found" to "无法下载这个 EPUB，请检查链接。",
    "podcast.episode_not_found" to "没有在 feed 中找到这一集。",
    "feed.episode_not_found" to "没有在 feed 中找到这一集。",
    "feed.scheme" to "播客 feed 地址无效。",
    "feed.parse" to "播客 feed 地址无效。",
    "feed.credentials" to "播客 feed 地址不能包含账号或密码。",
    "auth.required" to "登录已失效，请重新登录。",
    "auth.device_revoked" to "登录已失效，请重新登录。",
)
