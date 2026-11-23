package dev.trove.app.collection

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import dev.trove.app.library.collectionDownloadLabel
import dev.trove.app.library.consumptionLabel
import dev.trove.app.library.platformLabel
import dev.trove.app.library.processingLabel
import dev.trove.app.ui.components.TinyProgress
import dev.trove.app.ui.components.TroveCover
import dev.trove.app.ui.components.TroveIconButton
import dev.trove.app.ui.components.TroveRoundButton
import dev.trove.app.ui.components.coverText
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.library.LibraryItem
import dev.trove.playback.PlaybackState
import java.util.Locale

@Composable
fun CollectionScreen(
    collectionId: String,
    items: List<LibraryItem>,
    actionError: String?,
    playerState: PlaybackState,
    onClearError: () -> Unit,
    onBack: () -> Unit,
    onOpenItem: (String) -> Unit,
    onPlayItem: (String) -> Unit,
    onTogglePlay: () -> Unit,
    onRetryItem: (String) -> Unit,
    onRetryFailed: () -> Unit,
    onDownloadAll: () -> Unit,
    autoDownload: Boolean,
    onStopAutoDownload: () -> Unit,
    onDelete: (String) -> Unit,
) {
    val episodes = remember(items, collectionId) {
        sortCollectionEpisodes(items.filter { it.collectionId == collectionId })
    }
    var menuOpen by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }

    Scaffold(
        modifier = Modifier
            .fillMaxSize()
            .testTag("collection-screen"),
        containerColor = TroveColors.Paper,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
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
                TroveIconButton(
                    icon = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "返回",
                    onClick = onBack,
                )
                Text(
                    "合集",
                    style = MaterialTheme.typography.titleLarge,
                    color = TroveColors.Ink,
                    modifier = Modifier.padding(start = 8.dp),
                )
                Spacer(Modifier.weight(1f))
                Box {
                    TroveIconButton(
                        icon = Icons.Filled.MoreVert,
                        contentDescription = "更多",
                        onClick = { menuOpen = true },
                    )
                    DropdownMenu(
                        expanded = menuOpen,
                        onDismissRequest = { menuOpen = false },
                    ) {
                        if (autoDownload) {
                            DropdownMenuItem(
                                text = { Text("停止自动下载") },
                                onClick = {
                                    menuOpen = false
                                    onStopAutoDownload()
                                },
                                modifier = Modifier.testTag("collection-stop-auto-download"),
                            )
                        }
                        DropdownMenuItem(
                            text = { Text("删除合集", color = TroveColors.Danger) },
                            onClick = {
                                menuOpen = false
                                confirmDelete = true
                            },
                        )
                    }
                }
            }
            if (episodes.isEmpty()) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(28.dp),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text("合集还没有单集", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "重新添加合集链接可以补齐；已删除的单集不会自动恢复。",
                        style = MaterialTheme.typography.bodySmall,
                        color = TroveColors.Muted,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
                return@Column
            }

            val first = episodes.first()
            val coverItem = episodes.firstOrNull { it.coverArtifact != null } ?: first
            val title = first.collectionTitle ?: "合集"
            val platform = first.collectionPlatform ?: first.platform
            val completed = episodes.count { it.processingState == "completed" }
            val processing = episodes.count {
                it.processingState !in setOf("completed", "failed", "cancelled", "queued")
            }
            val queued = episodes.count { it.processingState == "queued" }
            val failed = episodes.count { it.processingState == "failed" }
            val finished = episodes.count { it.consumptionState == "finished" }
            val downloaded = episodes.count { it.downloadState == "completed" }
            val downloadable = episodes.count { it.artifacts.isNotEmpty() }
            val pendingDownloads = episodes.count {
                it.downloadState == "queued" || it.downloadState == "downloading"
            }
            val downloading = episodes.count { it.downloadState == "downloading" }
            val downloadFraction =
                if (episodes.isEmpty()) 0f else downloaded.toFloat() / episodes.size
            val allDownloaded = episodes.isNotEmpty() && downloaded == episodes.size
            val downloadColor = when {
                allDownloaded -> TroveColors.Green
                pendingDownloads > 0 -> TroveColors.Cooking
                else -> TroveColors.Muted
            }

            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .testTag("collection-episodes"),
                contentPadding = PaddingValues(bottom = 24.dp),
            ) {
                item(key = "header") {
                    Column(modifier = Modifier.padding(horizontal = 18.dp)) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(14.dp),
                        ) {
                            TroveCover(
                                item = coverItem,
                                size = 88.dp,
                                label = coverText(title, allowFullTitle = false),
                                seed = collectionId,
                            )
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    title,
                                    style = MaterialTheme.typography.titleLarge,
                                    color = TroveColors.Ink,
                                    maxLines = 2,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                Text(
                                    listOfNotNull(
                                        platformLabel(platform),
                                        first.author,
                                        "${episodes.size} 集",
                                    ).joinToString(" · "),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = TroveColors.Muted,
                                    modifier = Modifier.padding(top = 4.dp),
                                )
                            }
                        }
                        Row(
                            modifier = Modifier.padding(top = 10.dp),
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            if (processing > 0) StatusPill("$processing 处理中", TroveColors.Cooking, TroveColors.Gold.copy(alpha = 0.18f))
                            if (queued > 0) StatusPill("$queued 排队", TroveColors.Muted, TroveColors.Paper2)
                            if (failed > 0) StatusPill("$failed 失败", TroveColors.Danger, TroveColors.AccentSoft.copy(alpha = 0.35f))
                            if (completed > 0) StatusPill("$completed 处理完成", TroveColors.Green, TroveColors.Green.copy(alpha = 0.1f))
                        }
                        TinyProgress(
                            fraction = if (episodes.isEmpty()) 0f else completed.toFloat() / episodes.size,
                            modifier = Modifier.padding(top = 10.dp),
                        )
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(top = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text(
                                "处理进度 $completed/${episodes.size}",
                                style = MaterialTheme.typography.labelSmall,
                                color = TroveColors.Muted,
                            )
                            Text(
                                "已听 $finished/${episodes.size}",
                                style = MaterialTheme.typography.labelSmall,
                                color = TroveColors.Muted,
                            )
                        }
                        TinyProgress(
                            fraction = downloadFraction,
                            fill = when {
                                allDownloaded -> TroveColors.Green
                                pendingDownloads > 0 -> TroveColors.Cooking
                                else -> TroveColors.Accent
                            },
                            modifier = Modifier.padding(top = 8.dp),
                        )
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(top = 4.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text(
                                "已下载 $downloaded/${episodes.size}",
                                style = MaterialTheme.typography.labelSmall,
                                color = downloadColor,
                            )
                            Text(
                                "未下载 ${episodes.size - downloaded}",
                                style = MaterialTheme.typography.labelSmall,
                                color = TroveColors.Muted,
                            )
                        }
                        if (autoDownload) {
                            Text(
                                "已开启自动下载，新处理完成的单集会加入下载队列",
                                style = MaterialTheme.typography.labelSmall,
                                color = TroveColors.Muted,
                                modifier = Modifier
                                    .padding(top = 4.dp)
                                    .testTag("collection-auto-download-hint"),
                            )
                        }
                        if (downloadable > 0 || failed > 0) {
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                if (downloadable > 0) {
                                    val canStartDownload = downloadable > downloaded &&
                                        pendingDownloads == 0
                                    val downloadButtonLabel = when {
                                        allDownloaded -> "已全部下载"
                                        downloading > 0 -> "下载中 $downloaded/$downloadable"
                                        pendingDownloads > 0 -> "等待下载 $downloaded/$downloadable"
                                        downloadable > downloaded -> "下载全部"
                                        processing > 0 -> "等待处理完成"
                                        else -> "暂无可下载"
                                    }
                                    TextButton(
                                        onClick = onDownloadAll,
                                        enabled = canStartDownload,
                                        modifier = Modifier.testTag("collection-download-all"),
                                    ) {
                                        Text(downloadButtonLabel)
                                    }
                                }
                                if (failed > 0) {
                                    TextButton(
                                        onClick = onRetryFailed,
                                        modifier = Modifier.testTag("collection-retry-failed"),
                                    ) {
                                        Text("重试失败项")
                                    }
                                }
                            }
                        }
                        if (actionError != null) {
                            Surface(
                                shape = RoundedCornerShape(10.dp),
                                color = TroveColors.AccentSoft.copy(alpha = 0.35f),
                                contentColor = TroveColors.Danger,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(top = 6.dp),
                            ) {
                                Row(
                                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Text(
                                        actionError,
                                        style = MaterialTheme.typography.bodySmall,
                                        modifier = Modifier.weight(1f),
                                    )
                                    TextButton(onClick = onClearError) { Text("关闭") }
                                }
                            }
                        }
                        if (failed > 0) {
                            Surface(
                                shape = RoundedCornerShape(10.dp),
                                color = TroveColors.AccentSoft.copy(alpha = 0.28f),
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(top = 10.dp),
                            ) {
                                Text(
                                    "$failed 集处理失败，不影响其他集；可以单独重试。",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = TroveColors.Danger,
                                    modifier = Modifier.padding(10.dp),
                                )
                            }
                        }
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(top = 16.dp, bottom = 6.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text(
                                "单集",
                                style = MaterialTheme.typography.titleSmall,
                                color = TroveColors.Ink,
                            )
                            Text(
                                "最近消费优先",
                                style = MaterialTheme.typography.labelSmall,
                                color = TroveColors.Muted,
                            )
                        }
                    }
                }
                items(episodes, key = { it.id }) { item ->
                    val current = playerState.itemId == item.id
                    EpisodeRow(
                        item = item,
                        playing = current && playerState.isPlaying,
                        onOpen = { onOpenItem(item.id) },
                        onPlay = {
                            if (current) onTogglePlay() else onPlayItem(item.id)
                        },
                        onRetry = { onRetryItem(item.id) },
                    )
                }
            }
        }
    }

    if (confirmDelete) {
        DeleteCollectionDialog(
            title = episodes.firstOrNull()?.collectionTitle ?: "合集",
            count = episodes.size,
            onDismiss = { confirmDelete = false },
            onDelete = { mode ->
                confirmDelete = false
                onDelete(mode)
            },
        )
    }
}

internal fun sortCollectionEpisodes(items: List<LibraryItem>): List<LibraryItem> =
    items.sortedWith(
        compareByDescending<LibraryItem> { it.lastConsumedAt ?: Long.MIN_VALUE }
            .thenBy { it.collectionIndex ?: Int.MAX_VALUE }
            .thenBy { it.id }
    )

@Composable
private fun EpisodeRow(
    item: LibraryItem,
    playing: Boolean,
    onOpen: () -> Unit,
    onPlay: () -> Unit,
    onRetry: () -> Unit,
) {
    val failed = item.processingState == "failed"
    val ready = item.hasAudio || item.hasBook
    val errorMessage = item.errorMessage
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .testTag("collection-episode-${item.id}")
            .clickable(onClick = onOpen)
            .padding(horizontal = 18.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(9.dp),
    ) {
        Text(
            (item.collectionIndex ?: 0).toString().padStart(2, '0'),
            style = MaterialTheme.typography.labelSmall,
            color = TroveColors.Muted,
            modifier = Modifier.size(width = 22.dp, height = 16.dp),
        )
        TroveCover(
            item = item,
            size = 44.dp,
            label = coverText(item.title, item.collectionTitle, allowFullTitle = false),
        )
        Column(modifier = Modifier.weight(1f)) {
            Text(
                item.title,
                style = MaterialTheme.typography.titleSmall,
                color = TroveColors.Ink,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                modifier = Modifier.padding(top = 2.dp),
            ) {
                Text(
                    processingLabel(item.processingState),
                    style = MaterialTheme.typography.labelSmall,
                    color = when {
                        failed -> TroveColors.Danger
                        item.processingState == "completed" -> TroveColors.Green
                        item.isInbox -> TroveColors.Cooking
                        else -> TroveColors.Muted
                    },
                )
                if (item.durationSec != null) {
                    Text(
                        formatDuration(item.durationSec ?: 0.0),
                        style = MaterialTheme.typography.labelSmall,
                        color = TroveColors.Muted,
                    )
                }
                Text(
                    consumptionLabel(item.consumptionState),
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                )
                if (item.artifacts.isNotEmpty()) {
                    Text(
                        collectionDownloadLabel(item.downloadState),
                        style = MaterialTheme.typography.labelSmall,
                        color = when (item.downloadState) {
                            "completed" -> TroveColors.Green
                            "queued", "downloading" -> TroveColors.Cooking
                            "failed" -> TroveColors.Danger
                            else -> TroveColors.Muted
                        },
                    )
                }
            }
            if (errorMessage != null) {
                Text(
                    errorMessage,
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Danger,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        if (failed) {
            TextButton(onClick = onRetry) { Text("重试") }
        } else if (ready) {
            TroveRoundButton(
                icon = when {
                    item.isBookOnly -> Icons.AutoMirrored.Filled.MenuBook
                    playing -> Icons.Filled.Pause
                    else -> Icons.Filled.PlayArrow
                },
                contentDescription = when {
                    item.isBookOnly -> "阅读"
                    playing -> "暂停"
                    else -> "播放"
                },
                onClick = onPlay,
                size = 34.dp,
                iconSize = 16.dp,
                background = TroveColors.Paper2,
                border = TroveColors.Line,
                testTag = "collection-play-${item.id}",
            )
        } else {
            Box(
                modifier = Modifier
                    .size(34.dp)
                    .background(TroveColors.Paper2, CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Text("…", color = TroveColors.Muted)
            }
        }
    }
}

@Composable
private fun DeleteCollectionDialog(
    title: String,
    count: Int,
    onDismiss: () -> Unit,
    onDelete: (String) -> Unit,
) {
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false),
    ) {
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = TroveColors.Paper,
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .padding(18.dp),
        ) {
            Column(modifier = Modifier.padding(18.dp)) {
                Text("删除合集？", style = MaterialTheme.typography.titleLarge)
                Text(
                    "「$title」包含 $count 集。两种操作都会同步到 Host 和手机。",
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Muted,
                    modifier = Modifier.padding(top = 8.dp),
                )
                Surface(
                    onClick = { onDelete("delete_items") },
                    shape = RoundedCornerShape(13.dp),
                    color = TroveColors.AccentSoft.copy(alpha = 0.45f),
                    contentColor = TroveColors.Danger,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp)
                        .testTag("collection-delete-option-delete"),
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text("删除合集及全部 $count 集", style = MaterialTheme.typography.titleSmall)
                        Text(
                            "会从 Host 和手机移除，无法撤销。",
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(top = 2.dp),
                        )
                    }
                }
                Surface(
                    onClick = { onDelete("ungroup") },
                    shape = RoundedCornerShape(13.dp),
                    color = TroveColors.Paper2,
                    contentColor = TroveColors.Ink,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 9.dp)
                        .testTag("collection-delete-option-ungroup"),
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text("仅移除合集分组，保留 $count 集", style = MaterialTheme.typography.titleSmall)
                        Text(
                            "单集作为独立内容留在 Library，进度和文件不变。",
                            style = MaterialTheme.typography.labelSmall,
                            color = TroveColors.Muted,
                            modifier = Modifier.padding(top = 2.dp),
                        )
                    }
                }
                TextButton(
                    onClick = onDismiss,
                    modifier = Modifier.align(Alignment.CenterHorizontally),
                ) { Text("取消") }
            }
        }
    }
}

@Composable
private fun StatusPill(text: String, color: Color, background: Color) {
    Surface(
        shape = CircleShape,
        color = background,
        contentColor = color,
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp),
        )
    }
}

private fun formatDuration(value: Double): String {
    val seconds = value.toInt().coerceAtLeast(0)
    val hours = seconds / 3600
    val minutes = (seconds % 3600) / 60
    val remaining = seconds % 60
    return if (hours > 0) {
        String.format(Locale.getDefault(), "%d:%02d:%02d", hours, minutes, remaining)
    } else {
        String.format(Locale.getDefault(), "%d:%02d", minutes, remaining)
    }
}
