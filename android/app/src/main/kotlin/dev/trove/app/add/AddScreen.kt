package dev.trove.app.add

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dev.trove.app.library.processingLabel
import dev.trove.app.ui.components.RootTab
import dev.trove.app.ui.components.TroveBottomNav
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.network.FeedEpisodeDto

@Composable
fun AddScreen(
    viewModel: AddViewModel,
    onBack: () -> Unit,
    onLibrary: () -> Unit,
    onSearch: () -> Unit,
    onOpenItem: (String) -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(state.deduplicated, state.created?.id) {
        val created = state.created
        if (state.deduplicated && created != null) {
            viewModel.consumeDeduplicated()
            onOpenItem(created.id)
        }
    }
    Scaffold(
        modifier = Modifier.testTag("add-screen"),
        containerColor = TroveColors.Paper,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            TroveBottomNav(
                selected = RootTab.ADD,
                onSelect = {
                    when (it) {
                        RootTab.LIBRARY -> onLibrary()
                        RootTab.SEARCH -> onSearch()
                        RootTab.ADD -> Unit
                    }
                },
                modifier = Modifier.navigationBarsPadding(),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .statusBarsPadding(),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(start = 10.dp, end = 18.dp, top = 10.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Surface(
                    onClick = onBack,
                    shape = CircleShape,
                    color = Color.Transparent,
                    contentColor = TroveColors.Ink,
                ) {
                    Column(
                        modifier = Modifier
                            .size(40.dp)
                            .padding(8.dp),
                        verticalArrangement = Arrangement.Center,
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "返回")
                    }
                }
                Text(
                    "添加",
                    style = MaterialTheme.typography.titleLarge,
                    color = TroveColors.Ink,
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 18.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                FieldLabel("链接")
                OutlinedTextField(
                    value = state.url,
                    onValueChange = viewModel::updateUrl,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("add-url-input"),
                    placeholder = { Text("B 站 / YouTube 单条视频 URL") },
                    singleLine = true,
                    shape = RoundedCornerShape(12.dp),
                    colors = fieldColors(),
                )
                Surface(
                    onClick = viewModel::submitUrl,
                    shape = CircleShape,
                    color = TroveColors.Accent,
                    contentColor = TroveColors.White,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("add-submit"),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        if (state.submitting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                color = TroveColors.White,
                                strokeWidth = 2.dp,
                            )
                            Spacer(Modifier.size(8.dp))
                        }
                        Text(
                            if (state.submitting) "正在提交…" else "开始处理",
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(vertical = 13.dp),
                        )
                    }
                }
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = TroveColors.Paper2,
                    border = androidx.compose.foundation.BorderStroke(1.dp, TroveColors.Line),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text(
                            "本地音频 / 视频 / EPUB",
                            style = MaterialTheme.typography.labelMedium,
                            color = TroveColors.Ink,
                        )
                        Text(
                            "请在 Host Console 上传",
                            style = MaterialTheme.typography.labelSmall,
                            color = TroveColors.Muted,
                        )
                    }
                }
                FieldLabel("播客 feed")
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    OutlinedTextField(
                        value = state.feedUrl,
                        onValueChange = viewModel::updateFeed,
                        modifier = Modifier
                            .weight(1f)
                            .testTag("add-feed-input"),
                        placeholder = { Text("粘贴 RSS feed URL") },
                        singleLine = true,
                        shape = RoundedCornerShape(12.dp),
                        colors = fieldColors(),
                    )
                    TextButton(
                        onClick = viewModel::previewFeed,
                        modifier = Modifier.testTag("add-feed-preview"),
                    ) {
                        Text(if (state.previewing) "读取中…" else "预览")
                    }
                }
                val preview = state.preview
                if (preview != null) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(TroveColors.Paper2, RoundedCornerShape(12.dp))
                            .padding(12.dp),
                    ) {
                        Text(
                            preview.title,
                            style = MaterialTheme.typography.titleSmall,
                            color = TroveColors.Ink,
                        )
                        Text(
                            "${preview.episodes.size} 集 · 选择一集入库",
                            style = MaterialTheme.typography.labelSmall,
                            color = TroveColors.Muted,
                            modifier = Modifier.padding(bottom = 6.dp),
                        )
                        preview.episodes.take(10).forEach { episode ->
                            EpisodeRow(episode = episode, onClick = { viewModel.addEpisode(episode) })
                        }
                    }
                }
                Text(
                    "转写/书文本会分块发送给 DeepSeek 生成摘要和 Tag；Host 会执行 URL、平台、SSRF 和大小校验。",
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Muted,
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(TroveColors.Paper2, RoundedCornerShape(10.dp))
                        .padding(10.dp),
                )
                val error = state.error
                if (error != null) {
                    Text(
                        error,
                        style = MaterialTheme.typography.bodySmall,
                        color = TroveColors.Accent,
                        modifier = Modifier.testTag("add-error"),
                    )
                }
                val created = state.created
                if (created != null) {
                    AddStatusCard(
                        title = created.title,
                        state = created.processingState,
                        errorCode = created.errorCode,
                        error = created.errorMessage,
                        onRetry = viewModel::retry,
                        onOpen = if (created.processingState in setOf("completed", "failed", "cancelled")) {
                            { onOpenItem(created.id) }
                        } else {
                            null
                        },
                    )
                }
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}

@Composable
private fun EpisodeRow(episode: FeedEpisodeDto, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                episode.title,
                style = MaterialTheme.typography.bodyMedium,
                color = TroveColors.Ink,
                maxLines = 2,
            )
            Text(
                listOfNotNull(
                    episode.publishedAt,
                    episode.durationSec?.let { "${(it / 60).toInt()} 分钟" },
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
            )
        }
        Text("添加", style = MaterialTheme.typography.labelMedium, color = TroveColors.Accent)
    }
}

@Composable
private fun AddStatusCard(
    title: String,
    state: String,
    errorCode: String?,
    error: String?,
    onRetry: () -> Unit,
    onOpen: (() -> Unit)?,
) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = TroveColors.Paper2,
        border = androidx.compose.foundation.BorderStroke(1.dp, TroveColors.Line),
        modifier = Modifier
            .fillMaxWidth()
            .testTag("add-processing"),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, color = TroveColors.Ink)
            Text(
                processingLabel(state),
                style = MaterialTheme.typography.labelSmall,
                color = if (state == "failed") TroveColors.Danger else TroveColors.Cooking,
            )
            if (errorCode != null || error != null) {
                Text(
                    processingErrorLabel(errorCode, error),
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Danger,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (state == "failed") {
                    TextButton(onClick = onRetry) { Text("重试") }
                }
                if (onOpen != null) {
                    TextButton(onClick = onOpen) { Text("打开 Item") }
                }
            }
        }
    }
}

@Composable
private fun FieldLabel(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.labelMedium,
        color = TroveColors.Muted,
    )
}

@Composable
private fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = TroveColors.Line,
    unfocusedBorderColor = TroveColors.Line,
    focusedContainerColor = TroveColors.Paper2,
    unfocusedContainerColor = TroveColors.Paper2,
    focusedTextColor = TroveColors.Ink,
    unfocusedTextColor = TroveColors.Ink,
    cursorColor = TroveColors.Accent,
)

private fun processingErrorLabel(code: String?, message: String?): String = when {
    code == null -> message ?: "处理失败，请重试。"
    code.startsWith("network.") -> "网络错误，请检查 Host 连接后重试。"
    code.startsWith("auth.") -> "登录已失效，请重新登录。"
    code.startsWith("drm.") -> "内容受 DRM 保护，无法处理。"
    code.startsWith("asr.") -> "转写失败，请重试或检查音频。"
    code.startsWith("llm.") -> "摘要/Tag 生成失败，请重试。"
    code.startsWith("storage.") -> "Host 存储失败，请检查磁盘空间。"
    code.startsWith("download.") -> "Host 下载源文件失败，请重试。"
    code.startsWith("unsupported.") -> "Host 不支持这条内容。"
    code.startsWith("parse.") -> "内容解析失败。"
    code == "item.not_found" -> "Item 已不存在。"
    else -> message?.takeIf { it.isNotBlank() } ?: "处理失败（$code）。"
}
