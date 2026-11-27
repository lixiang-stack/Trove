package dev.trove.app.add

import androidx.compose.foundation.BorderStroke
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dev.trove.app.library.processingLabel
import dev.trove.app.ui.components.RootTab
import dev.trove.app.ui.components.TroveBottomNav
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.network.CollectionCreateResponseDto
import dev.trove.core.network.FeedEpisodeDto
import dev.trove.core.network.ItemDto
import dev.trove.core.network.LinkEpisodeDto
import dev.trove.core.network.LinkInspectResponseDto

@Composable
fun AddScreen(
    viewModel: AddViewModel,
    onBack: () -> Unit,
    onLibrary: () -> Unit,
    onSearch: () -> Unit,
    onOpenItem: (String) -> Unit,
    onOpenCollection: (String) -> Unit,
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
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                FieldLabel("链接")
                OutlinedTextField(
                    value = state.url,
                    onValueChange = viewModel::updateUrl,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("add-url-input"),
                    placeholder = { Text("B 站 / YouTube 视频或合集、EPUB 直链、播客 feed") },
                    singleLine = true,
                    shape = RoundedCornerShape(12.dp),
                    colors = fieldColors(),
                )
                Text(
                    "粘贴后自动识别，不会立即下载。",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                )
                Surface(
                    onClick = viewModel::detectNow,
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
                        if (state.detecting || state.submitting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                color = TroveColors.White,
                                strokeWidth = 2.dp,
                            )
                            Spacer(Modifier.size(8.dp))
                        }
                        Text(
                            when {
                                state.submitting -> "正在提交…"
                                state.detecting -> "识别中…"
                                state.inspection != null -> "重新识别"
                                else -> "识别链接"
                            },
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(vertical = 13.dp),
                        )
                    }
                }

                if (state.detecting) {
                    DetectingCard()
                }

                val error = state.error
                if (error != null) {
                    Text(
                        error,
                        style = MaterialTheme.typography.bodySmall,
                        color = TroveColors.Accent,
                        modifier = Modifier.testTag("add-error"),
                    )
                }

                val inspection = state.inspection
                if (!state.detecting && inspection != null) {
                    PreviewCard(
                        inspection = inspection,
                        submitting = state.submitting,
                        onSubmit = viewModel::submit,
                        onAddEpisode = viewModel::addEpisode,
                    )
                }

                val createdCollection = state.createdCollection
                if (createdCollection != null) {
                    CollectionResultCard(
                        result = createdCollection,
                        onOpen = { onOpenCollection(createdCollection.collection.id) },
                        onContinue = viewModel::clearResult,
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

                SupportHint()
                Text(
                    "转写/书文本会分块发送给 DeepSeek 生成摘要和标签；Host 会执行 URL、平台、SSRF 和大小校验。",
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Muted,
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(TroveColors.Paper2, RoundedCornerShape(10.dp))
                        .padding(10.dp),
                )
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}

@Composable
private fun DetectingCard() {
    Surface(
        shape = RoundedCornerShape(14.dp),
        color = TroveColors.Paper2,
        border = BorderStroke(1.dp, TroveColors.Line),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            CircularProgressIndicator(
                modifier = Modifier.size(18.dp),
                color = TroveColors.Accent,
                strokeWidth = 2.dp,
            )
            Column {
                Text("正在识别链接", style = MaterialTheme.typography.titleSmall)
                Text(
                    "读取标题、集数和时长，不会下载媒体。通常需要 2–10 秒。",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                )
            }
        }
    }
}

@Composable
private fun PreviewCard(
    inspection: LinkInspectResponseDto,
    submitting: Boolean,
    onSubmit: () -> Unit,
    onAddEpisode: (FeedEpisodeDto) -> Unit,
) {
    val kind = inspection.kind
    val coverTone = when (kind) {
        "collection" -> "合"
        "ebook" -> "书"
        "podcast_feed" -> "播"
        else -> "单"
    }
    Surface(
        shape = RoundedCornerShape(15.dp),
        color = TroveColors.Paper2,
        border = BorderStroke(1.dp, TroveColors.Line),
        modifier = Modifier
            .fillMaxWidth()
            .testTag("add-preview"),
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Surface(
                    shape = RoundedCornerShape(13.dp),
                    color = if (kind == "collection") TroveColors.Green else TroveColors.Gold,
                    modifier = Modifier.size(64.dp),
                ) {
                    Column(
                        verticalArrangement = Arrangement.Center,
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            coverTone,
                            style = MaterialTheme.typography.headlineMedium,
                            color = TroveColors.White,
                        )
                    }
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        kindLabel(kind),
                        style = MaterialTheme.typography.labelSmall,
                        color = TroveColors.Muted,
                    )
                    Text(
                        inspection.title,
                        style = MaterialTheme.typography.titleLarge,
                        color = TroveColors.Ink,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        previewMeta(inspection),
                        style = MaterialTheme.typography.labelSmall,
                        color = TroveColors.Muted,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }

            if (
                inspection.ignoredPlaylist &&
                inspection.warnings.none { it.code == "link.ignored_playlist" }
            ) {
                PreviewNotice("链接里的播放列表参数已忽略，只添加当前视频。")
            }
            inspection.warnings.forEach { warning ->
                PreviewNotice(
                    warning.message,
                    danger = warning.code == "collection.episode_conflict",
                )
            }

            if (kind == "collection" && inspection.episodes.isNotEmpty()) {
                Column(modifier = Modifier.padding(top = 10.dp)) {
                    inspection.episodes.take(3).forEach { episode ->
                        EpisodePreviewRow(episode)
                    }
                    if (inspection.episodeCount > 3) {
                        Text(
                            "+ ${inspection.episodeCount - 3} 集 · 按上游顺序处理",
                            style = MaterialTheme.typography.labelSmall,
                            color = TroveColors.Muted,
                            modifier = Modifier.padding(top = 6.dp),
                        )
                    }
                }
            }

            if (kind == "podcast_feed") {
                val feed = inspection.feed
                if (feed != null) {
                    Text(
                        "${feed.title} · 选择一集入库",
                        style = MaterialTheme.typography.labelSmall,
                        color = TroveColors.Muted,
                        modifier = Modifier.padding(top = 10.dp),
                    )
                    feed.episodes.take(10).forEach { episode ->
                        FeedEpisodeRow(episode = episode, onClick = { onAddEpisode(episode) })
                    }
                    if (feed.episodes.size > 10) {
                        Text(
                            "查看全部 ${feed.episodes.size} 集请使用 Host Console。",
                            style = MaterialTheme.typography.labelSmall,
                            color = TroveColors.Muted,
                        )
                    }
                }
            } else {
                Surface(
                    onClick = onSubmit,
                    shape = CircleShape,
                    color = TroveColors.Accent,
                    contentColor = TroveColors.White,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp)
                        .testTag("add-preview-submit"),
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.Center,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        if (submitting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                color = TroveColors.White,
                                strokeWidth = 2.dp,
                            )
                            Spacer(Modifier.size(8.dp))
                        }
                        Text(
                            when (kind) {
                                "collection" -> "添加合集（${inspection.episodeCount} 集）"
                                "ebook" -> "添加电子书"
                                else -> "开始处理"
                            },
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(vertical = 12.dp),
                        )
                    }
                }
            }
            if (kind == "collection") {
                Text(
                    "将全部处理，可能需要较长时间；单集失败不影响其他集。",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
            if (kind == "ebook") {
                Text(
                    "书名、作者和封面会在下载解析后更新。",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
        }
    }
}

@Composable
private fun PreviewNotice(text: String, danger: Boolean = false) {
    Surface(
        shape = RoundedCornerShape(10.dp),
        color = if (danger) TroveColors.AccentSoft.copy(alpha = 0.35f) else TroveColors.Paper2,
        border = BorderStroke(1.dp, TroveColors.Line),
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp),
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            color = if (danger) TroveColors.Danger else TroveColors.Muted,
            modifier = Modifier.padding(9.dp),
        )
    }
}

@Composable
private fun EpisodePreviewRow(episode: LinkEpisodeDto) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            episode.index.toString().padStart(2, '0'),
            style = MaterialTheme.typography.labelSmall,
            color = TroveColors.Muted,
            modifier = Modifier.size(width = 22.dp, height = 16.dp),
        )
        Text(
            episode.title,
            style = MaterialTheme.typography.bodySmall,
            color = TroveColors.Ink,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
        Text(
            episode.durationSec?.let(::formatDuration) ?: "—",
            style = MaterialTheme.typography.labelSmall,
            color = TroveColors.Muted,
        )
    }
}

@Composable
private fun FeedEpisodeRow(episode: FeedEpisodeDto, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                episode.title,
                style = MaterialTheme.typography.bodyMedium,
                color = TroveColors.Ink,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                listOfNotNull(
                    episode.publishedAt,
                    episode.durationSec?.let(::formatDuration),
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
            )
        }
        Text("添加", style = MaterialTheme.typography.labelMedium, color = TroveColors.Accent)
    }
}

@Composable
private fun CollectionResultCard(
    result: CollectionCreateResponseDto,
    onOpen: () -> Unit,
    onContinue: () -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(15.dp),
        color = TroveColors.Paper2,
        border = BorderStroke(1.dp, TroveColors.Line),
        modifier = Modifier
            .fillMaxWidth()
            .testTag("add-collection-result"),
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text("合集已加入", style = MaterialTheme.typography.titleMedium, color = TroveColors.Green)
            Text(
                result.collection.title,
                style = MaterialTheme.typography.titleLarge,
                color = TroveColors.Ink,
                modifier = Modifier.padding(top = 6.dp),
            )
            Text(
                "${result.collection.episodeCount} 集 · 新增 ${result.addedCount} · 并入 ${result.attachedCount}" +
                    if (result.skippedCount > 0) " · 跳过 ${result.skippedCount}" else "",
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
            )
            Row(
                modifier = Modifier.padding(top = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Surface(
                    onClick = onOpen,
                    shape = CircleShape,
                    color = TroveColors.Accent,
                    contentColor = TroveColors.White,
                ) {
                    Text(
                        "打开合集",
                        style = MaterialTheme.typography.labelLarge,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                    )
                }
                TextButton(onClick = onContinue) { Text("继续添加") }
            }
            Text(
                "可以离开此页，Host 会继续处理；失败单集可以在合集详情单独重试。",
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}

@Composable
private fun SupportHint() {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = TroveColors.Paper2,
        border = BorderStroke(1.dp, TroveColors.Line),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text("支持自动识别", style = MaterialTheme.typography.labelMedium, color = TroveColors.Ink)
            Text(
                "单集视频 · 视频合集 · EPUB 直链 · 播客 feed",
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
                modifier = Modifier.padding(top = 2.dp),
            )
            Text(
                "本地音频/视频/EPUB 请在 Host Console 上传。",
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
                modifier = Modifier.padding(top = 2.dp),
            )
        }
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
        border = BorderStroke(1.dp, TroveColors.Line),
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

private fun kindLabel(kind: String): String = when (kind) {
    "video" -> "识别为 · 单集视频"
    "collection" -> "识别为 · 视频合集"
    "ebook" -> "识别为 · 电子书"
    "podcast_feed" -> "识别为 · 播客 feed"
    else -> "识别结果"
}

private fun previewMeta(inspection: LinkInspectResponseDto): String = listOfNotNull(
    inspection.platform,
    inspection.author,
    if (inspection.kind == "collection") {
        "${inspection.episodeCount} 集" +
            (inspection.totalDurationSec?.let { " · 约 ${formatDuration(it)}" } ?: " · 时长未知")
    } else if (inspection.kind == "ebook") {
        inspection.fileSize?.let { formatBytes(it) }
    } else {
        inspection.durationSec?.let(::formatDuration)
    },
).joinToString(" · ")

private fun formatDuration(value: Double): String {
    val seconds = value.toInt().coerceAtLeast(0)
    val hours = seconds / 3600
    val minutes = (seconds % 3600) / 60
    val remaining = seconds % 60
    return if (hours > 0) {
        String.format(java.util.Locale.getDefault(), "%d:%02d:%02d", hours, minutes, remaining)
    } else {
        String.format(java.util.Locale.getDefault(), "%d:%02d", minutes, remaining)
    }
}

private fun formatBytes(value: Long): String {
    if (value <= 0) return "—"
    val units = listOf("B", "KB", "MB", "GB")
    var size = value.toDouble()
    var index = 0
    while (size >= 1024 && index < units.lastIndex) {
        size /= 1024
        index += 1
    }
    return String.format(java.util.Locale.getDefault(), "%.1f %s", size, units[index])
}

private fun processingErrorLabel(code: String?, message: String?): String = when {
    code == null -> message ?: "处理失败，请重试。"
    code.startsWith("network.") -> "网络错误，请检查 Host 连接后重试。"
    code.startsWith("auth.") -> "登录已失效，请重新登录。"
    code.startsWith("drm.") -> "内容受 DRM 保护，无法处理。"
    code.startsWith("asr.") -> "转写失败，请重试或检查音频。"
    code.startsWith("llm.") -> "摘要/标签 生成失败，请重试。"
    code.startsWith("storage.") -> "Host 存储失败，请检查磁盘空间。"
    code.startsWith("download.") -> "Host 下载源文件失败，请重试。"
    code.startsWith("ebook.") -> "EPUB 下载或解析失败。"
    code.startsWith("unsupported.") -> "Host 不支持这条内容。"
    code.startsWith("parse.") -> "内容解析失败。"
    code == "item.not_found" -> "Item 已不存在。"
    else -> message?.takeIf { it.isNotBlank() } ?: "处理失败（$code）。"
}
