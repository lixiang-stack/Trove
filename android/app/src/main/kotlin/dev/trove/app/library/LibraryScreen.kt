package dev.trove.app.library

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Headphones
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import dev.trove.app.R
import dev.trove.app.ui.components.RootTab
import dev.trove.app.ui.components.TinyProgress
import dev.trove.app.ui.components.TroveBottomNav
import dev.trove.app.ui.components.TroveChip
import dev.trove.app.ui.components.TroveCover
import dev.trove.app.ui.components.TroveEmpty
import dev.trove.app.ui.components.TroveIconButton
import dev.trove.app.ui.components.TroveRoundButton
import dev.trove.app.ui.components.coverText
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.library.LibraryItem
import dev.trove.core.transcript.TranscriptParser
import dev.trove.core.transcript.TranscriptSegment
import dev.trove.playback.PlaybackState
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

private enum class QuickFilter(val label: String) {
    ALL("全部"),
    IN_PROGRESS("进行中"),
    PROCESSING("处理中"),
    FINISHED("已完成"),
}

@Composable
fun LibraryScreen(
    state: LibraryUiState,
    selectedItemId: String?,
    playerState: PlaybackState,
    transcript: List<TranscriptSegment>,
    onRefresh: () -> Unit,
    onOpenItem: (String) -> Unit,
    onOpenCollection: (String) -> Unit,
    onQuickPlay: (String) -> Unit,
    onTogglePlay: () -> Unit,
    onSeek: (Long) -> Unit,
    onSpeed: (Float) -> Unit,
    onTranscript: () -> Unit,
    onDownloads: () -> Unit,
    onDevices: () -> Unit,
    onSignOut: () -> Unit,
    onSearch: () -> Unit,
    onAdd: () -> Unit,
    onSort: (LibrarySort) -> Unit,
    onInbox: (Boolean) -> Unit,
    onClearFilters: () -> Unit,
    onType: (String?) -> Unit,
    onConsumption: (String?) -> Unit,
    onTag: (String?) -> Unit,
    onSource: (String?) -> Unit,
    onSettings: () -> Unit,
    onDismissConflict: () -> Unit,
    onClearCollectionActionError: () -> Unit,
) {
    LifecycleResumeEffect(Unit) {
        onRefresh()
        onPauseOrDispose { }
    }
    var filterOpen by remember { mutableStateOf(false) }
    var menuOpen by remember { mutableStateOf(false) }
    val quick = state.filters.quickFilter()
    val advancedCount = listOfNotNull(
        state.filters.type,
        state.filters.tag,
        state.filters.source,
    ).size
    Scaffold(
        modifier = Modifier
            .fillMaxSize()
            .testTag("library-screen"),
        containerColor = TroveColors.Paper,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            TroveBottomNav(
                selected = RootTab.LIBRARY,
                onSelect = {
                    when (it) {
                        RootTab.SEARCH -> onSearch()
                        RootTab.ADD -> onAdd()
                        RootTab.LIBRARY -> Unit
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
                    .padding(start = 18.dp, end = 10.dp, top = 14.dp, bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text(
                            "拾藏",
                            style = MaterialTheme.typography.displaySmall,
                            color = TroveColors.Ink,
                        )
                        Text(
                            "TROVE",
                            style = MaterialTheme.typography.labelSmall,
                            color = TroveColors.Muted,
                            modifier = Modifier.padding(start = 8.dp, bottom = 5.dp),
                        )
                    }
                    Text(
                        buildString {
                            append("${state.entries.size} 条内容")
                            val collections = state.entries.count { it is LibraryEntry.CollectionCard }
                            if (collections > 0) append(" · $collections 个合集")
                        },
                        style = MaterialTheme.typography.labelMedium,
                        color = TroveColors.Muted,
                    )
                }
                Box {
                    TroveIconButton(
                        icon = Icons.Filled.MoreVert,
                        contentDescription = "更多",
                        onClick = { menuOpen = true },
                    )
                    DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                        DropdownMenuItem(
                            text = { Text("下载管理") },
                            onClick = {
                                menuOpen = false
                                onDownloads()
                            },
                        )
                        DropdownMenuItem(
                            text = { Text("设置") },
                            onClick = {
                                menuOpen = false
                                onSettings()
                            },
                        )
                        DropdownMenuItem(
                            text = { Text(stringResource(R.string.login_devices)) },
                            onClick = {
                                menuOpen = false
                                onDevices()
                            },
                        )
                        DropdownMenuItem(
                            text = { Text(stringResource(R.string.login_sign_out)) },
                            onClick = {
                                menuOpen = false
                                onSignOut()
                            },
                        )
                    }
                }
            }
            SyncStrip(state = state, onRefresh = onRefresh)
            if (state.conflictNotice != null) {
                ConflictStrip(
                    message = state.conflictNotice,
                    onDismiss = onDismissConflict,
                )
            }
            if (state.collectionActionError != null) {
                ConflictStrip(
                    message = state.collectionActionError,
                    onDismiss = onClearCollectionActionError,
                )
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 18.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                QuickFilter.entries.forEach { filter ->
                    TroveChip(
                        label = filter.label,
                        selected = quick == filter,
                        onClick = {
                            when (filter) {
                                QuickFilter.ALL -> {
                                    onInbox(false)
                                    onConsumption(null)
                                }

                                QuickFilter.IN_PROGRESS -> {
                                    onInbox(false)
                                    onConsumption("in_progress")
                                }

                                QuickFilter.PROCESSING -> {
                                    onInbox(true)
                                    onConsumption(null)
                                }

                                QuickFilter.FINISHED -> {
                                    onInbox(false)
                                    onConsumption("finished")
                                }
                            }
                        },
                        testTag = if (filter == QuickFilter.PROCESSING) "filter-inbox" else null,
                    )
                }
                TroveChip(
                    label = if (advancedCount > 0) "筛选 ($advancedCount)" else "筛选",
                    selected = advancedCount > 0,
                    onClick = { filterOpen = true },
                    testTag = "filter-button",
                )
                Surface(
                    onClick = { filterOpen = true },
                    shape = CircleShape,
                    color = Color.Transparent,
                    contentColor = TroveColors.Muted,
                ) {
                    Box(Modifier.size(32.dp), contentAlignment = Alignment.Center) {
                        androidx.compose.material3.Icon(
                            Icons.Filled.Tune,
                            contentDescription = "筛选",
                            modifier = Modifier.size(17.dp),
                        )
                    }
                }
            }
            when {
                state.loading -> Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator(color = TroveColors.Accent, strokeWidth = 2.dp)
                        Spacer(Modifier.height(12.dp))
                        Text(
                            stringResource(R.string.library_syncing),
                            color = TroveColors.Muted,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }

                state.errorCode != null && state.allItems.isEmpty() -> TroveEmpty(
                    title = stringResource(R.string.library_sync_failed, state.errorCode),
                    copy = "请检查 Host 地址和网络。",
                    action = stringResource(R.string.library_retry),
                    onAction = onRefresh,
                )

                state.entries.isEmpty() -> TroveEmpty(
                    title = if (state.allItems.isEmpty()) {
                        stringResource(R.string.library_empty)
                    } else {
                        stringResource(R.string.library_no_matches)
                    },
                    copy = if (state.allItems.isEmpty()) {
                        "从链接、文件或播客 feed 开始。"
                    } else {
                        "换个筛选条件试试。"
                    },
                    action = if (state.filters.hasAny) {
                        stringResource(R.string.filter_clear)
                    } else {
                        "添加第一条内容"
                    },
                    onAction = if (state.filters.hasAny) onClearFilters else onAdd,
                )

                else -> LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 20.dp),
                ) {
                    itemsIndexed(state.entries, key = { _, entry -> entry.id }) { index, entry ->
                        when (entry) {
                            is LibraryEntry.CollectionCard -> {
                                CollectionRow(
                                    entry = entry,
                                    onOpen = { onOpenCollection(entry.collectionId) },
                                )
                                HorizontalDivider(color = TroveColors.Line)
                            }

                            is LibraryEntry.Single -> {
                                val item = entry.item
                                val selected = selectedItemId == item.id
                                val current = playerState.itemId == item.id
                                QueueRow(
                                    item = item,
                                    index = index,
                                    active = selected,
                                    playing = current && playerState.isPlaying,
                                    onOpen = { onOpenItem(item.id) },
                                    onPlay = {
                                        if (current) onTogglePlay() else onQuickPlay(item.id)
                                    },
                                )
                                if (selected && current) {
                                    InlinePlayer(
                                        item = item,
                                        playback = playerState,
                                        transcript = transcript,
                                        onToggle = onTogglePlay,
                                        onSeek = onSeek,
                                        onSpeed = onSpeed,
                                        onTranscript = onTranscript,
                                    )
                                }
                                HorizontalDivider(color = TroveColors.Line)
                            }
                        }
                    }
                }
            }
        }
    }
    if (filterOpen) {
        FilterDialog(
            state = state,
            onDismiss = { filterOpen = false },
            onType = onType,
            onConsumption = onConsumption,
            onTag = onTag,
            onSource = onSource,
            onSort = onSort,
            onClear = onClearFilters,
        )
    }
}

private fun LibraryFilters.quickFilter(): QuickFilter = when {
    inbox -> QuickFilter.PROCESSING
    consumption == "in_progress" -> QuickFilter.IN_PROGRESS
    consumption == "finished" -> QuickFilter.FINISHED
    else -> QuickFilter.ALL
}

@Composable
private fun ConflictStrip(message: String, onDismiss: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp, vertical = 2.dp)
            .background(TroveColors.AccentSoft.copy(alpha = 0.35f), RoundedCornerShape(10.dp))
            .padding(start = 12.dp, end = 4.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            message,
            style = MaterialTheme.typography.labelSmall,
            color = TroveColors.Ink,
            modifier = Modifier.weight(1f),
        )
        Surface(
            onClick = onDismiss,
            shape = CircleShape,
            color = Color.Transparent,
            contentColor = TroveColors.Muted,
        ) {
            Box(Modifier.size(32.dp), contentAlignment = Alignment.Center) {
                androidx.compose.material3.Icon(
                    Icons.Filled.Close,
                    contentDescription = "关闭提示",
                    modifier = Modifier.size(15.dp),
                )
            }
        }
    }
}

@Composable
private fun SyncStrip(state: LibraryUiState, onRefresh: () -> Unit) {
    if (!state.syncing && !state.offline && state.errorCode == null && state.lastSuccessAt == null) {
        return
    }
    val text = when {
        state.syncing -> stringResource(R.string.library_syncing)
        state.offline -> stringResource(R.string.library_offline)
        state.errorCode != null -> stringResource(R.string.library_sync_failed, state.errorCode)
        state.queuedDownloads > 0 ->
            stringResource(R.string.library_sync_queued_downloads, state.queuedDownloads)
        else -> "已同步"
    }
    val color = when {
        state.errorCode != null -> TroveColors.Danger
        state.offline -> TroveColors.Cooking
        state.queuedDownloads > 0 -> TroveColors.Cooking
        else -> TroveColors.Muted
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelSmall,
            color = color,
            modifier = Modifier
                .weight(1f)
                .testTag("sync-status"),
        )
        TextButton(
            onClick = onRefresh,
            modifier = Modifier.testTag("sync-retry"),
        ) {
            androidx.compose.material3.Icon(
                Icons.Filled.Refresh,
                contentDescription = null,
                modifier = Modifier.size(14.dp),
                tint = color,
            )
            Spacer(Modifier.width(4.dp))
            Text(stringResource(R.string.library_retry), style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun CollectionRow(entry: LibraryEntry.CollectionCard, onOpen: () -> Unit) {
    val statusText = when {
        entry.failedCount > 0 && entry.processingCount > 0 ->
            "${entry.processingCount} 处理中 · ${entry.failedCount} 失败"
        entry.failedCount > 0 -> "${entry.failedCount} 集失败"
        entry.processingCount > 0 || entry.queuedCount > 0 ->
            listOfNotNull(
                entry.processingCount.takeIf { it > 0 }?.let { "$it 处理中" },
                entry.queuedCount.takeIf { it > 0 }?.let { "$it 排队" },
            ).joinToString(" · ")
        entry.completedCount < entry.episodeCount ->
            "处理 ${entry.completedCount}/${entry.episodeCount}"
        entry.allDownloaded -> "已全部下载"
        entry.downloadingCount > 0 ->
            "下载中 ${entry.downloadedCount}/${entry.episodeCount}"
        entry.pendingDownloadCount > 0 ->
            "等待下载 ${entry.downloadedCount}/${entry.episodeCount}"
        else -> "已下载 ${entry.downloadedCount}/${entry.episodeCount}"
    }
    val statusColor = when {
        entry.failedCount > 0 -> TroveColors.Danger
        entry.processingCount > 0 || entry.queuedCount > 0 -> TroveColors.Cooking
        entry.pendingDownloadCount > 0 -> TroveColors.Cooking
        entry.allDownloaded -> TroveColors.Green
        else -> TroveColors.Muted
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .testTag("library-collection-${entry.collectionId}")
            .clickable(onClick = onOpen)
            .padding(horizontal = 18.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        TroveCover(
            item = entry.coverItem,
            size = 52.dp,
            label = coverText(entry.title, allowFullTitle = false),
            seed = entry.collectionId,
        )
        Column(modifier = Modifier.weight(1f)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                Text(
                    entry.title,
                    style = MaterialTheme.typography.titleSmall,
                    color = TroveColors.Ink,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                Surface(
                    shape = RoundedCornerShape(999.dp),
                    color = TroveColors.AccentSoft.copy(alpha = 0.45f),
                    contentColor = TroveColors.Accent,
                ) {
                    Text(
                        "合集",
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(horizontal = 7.dp, vertical = 2.dp),
                    )
                }
            }
            Text(
                listOfNotNull(
                    platformLabel(entry.platform),
                    entry.author,
                    "${entry.episodeCount} 集",
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 2.dp),
            )
            Text(
                statusText,
                style = MaterialTheme.typography.labelSmall,
                color = statusColor,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 2.dp),
            )
            TinyProgress(
                fraction = entry.downloadProgress,
                fill = when {
                    entry.allDownloaded -> TroveColors.Green
                    entry.pendingDownloadCount > 0 -> TroveColors.Cooking
                    else -> TroveColors.Accent
                },
                modifier = Modifier.padding(top = 4.dp),
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 2.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    "已听 ${entry.finishedCount}/${entry.episodeCount}",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                )
                Text(
                    "处理 ${entry.completedCount}/${entry.episodeCount}",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                )
            }
        }
        Box(
            modifier = Modifier
                .size(34.dp)
                .clip(CircleShape)
                .background(TroveColors.Paper2),
            contentAlignment = Alignment.Center,
        ) {
            Text("›", style = MaterialTheme.typography.titleMedium, color = TroveColors.Ink)
        }
    }
}

@Composable
private fun QueueRow(
    item: LibraryItem,
    index: Int,
    active: Boolean,
    playing: Boolean,
    onOpen: () -> Unit,
    onPlay: () -> Unit,
) {
    val isBook = item.isBookOnly
    val ready = item.processingState in setOf("completed", "failed", "cancelled") ||
        item.artifacts.isNotEmpty()
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(if (active) TroveColors.Paper2 else Color.Transparent)
            .testTag("library-item-${item.id}")
            .clickable(onClick = onOpen)
            .padding(horizontal = 18.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(
            text = (index + 1).toString().padStart(2, '0'),
            style = MaterialTheme.typography.labelSmall,
            color = TroveColors.Muted,
            modifier = Modifier.width(20.dp),
        )
        TroveCover(item, size = 48.dp)
        Column(modifier = Modifier.weight(1f)) {
            Text(
                item.title,
                style = MaterialTheme.typography.titleSmall,
                color = TroveColors.Ink,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                metaLine(item),
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 2.dp),
            )
            Text(
                progressLine(item),
                style = MaterialTheme.typography.labelSmall,
                color = statusColor(item),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 2.dp),
            )
            val fraction = progressFraction(item)
            if (fraction > 0f) {
                TinyProgress(
                    fraction = fraction,
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }
        when {
            !ready -> Box(
                Modifier
                    .size(34.dp)
                    .clip(CircleShape)
                    .background(TroveColors.Ink.copy(alpha = 0.04f)),
                contentAlignment = Alignment.Center,
            ) {
                androidx.compose.material3.Icon(
                    if (item.processingState == "failed") {
                        Icons.Outlined.ErrorOutline
                    } else {
                        Icons.Filled.Headphones
                    },
                    contentDescription = null,
                    tint = TroveColors.Muted,
                    modifier = Modifier.size(16.dp),
                )
            }

            else -> TroveRoundButton(
                icon = when {
                    isBook -> Icons.AutoMirrored.Filled.MenuBook
                    playing -> Icons.Filled.Pause
                    else -> Icons.Filled.PlayArrow
                },
                contentDescription = if (isBook) "阅读" else if (playing) "暂停" else "播放",
                onClick = onPlay,
                size = 34.dp,
                iconSize = 16.dp,
                background = TroveColors.Paper2,
                border = TroveColors.Line,
                testTag = "play-${item.id}",
            )
        }
    }
}

@Composable
private fun InlinePlayer(
    item: LibraryItem,
    playback: PlaybackState,
    transcript: List<TranscriptSegment>,
    onToggle: () -> Unit,
    onSeek: (Long) -> Unit,
    onSpeed: (Float) -> Unit,
    onTranscript: () -> Unit,
) {
    val durationMs = playback.durationMs.takeIf { it > 0 }
        ?: ((item.durationSec ?: 0.0) * 1000).toLong()
    val positionMs = playback.positionMs.coerceAtLeast(0)
    val fraction = if (durationMs > 0) positionMs.toFloat() / durationMs else 0f
    Column(modifier = Modifier.padding(horizontal = 18.dp, vertical = 4.dp)) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(14.dp))
                .background(TroveColors.Player)
                .padding(12.dp),
        ) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(
                    TranscriptParser.timestamp(positionMs),
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Paper.copy(alpha = 0.55f),
                )
                Text(
                    TranscriptParser.timestamp(durationMs),
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Paper.copy(alpha = 0.55f),
                )
            }
            TinyProgress(
                fraction = fraction,
                modifier = Modifier.padding(top = 5.dp),
                track = Color.White.copy(alpha = 0.16f),
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                TextButton(onClick = { onSpeed(nextSpeed(playback.speed)) }) {
                    Text(
                        "${speedLabel(playback.speed)}×",
                        color = TroveColors.Paper,
                        style = MaterialTheme.typography.labelMedium,
                    )
                }
                TroveRoundButton(
                    icon = if (playback.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                    contentDescription = if (playback.isPlaying) "暂停" else "播放",
                    onClick = onToggle,
                    size = 36.dp,
                    iconSize = 17.dp,
                    background = TroveColors.Accent,
                    contentColor = TroveColors.White,
                )
                TextButton(onClick = onTranscript) {
                    Text(
                        "Transcript",
                        color = TroveColors.AccentSoft,
                        style = MaterialTheme.typography.labelMedium,
                    )
                }
            }
        }
        if (transcript.isNotEmpty()) {
            transcript.take(2).forEach { segment ->
                Row(
                    modifier = Modifier.padding(top = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text(
                        TranscriptParser.timestamp(segment.startMs),
                        style = MaterialTheme.typography.labelSmall,
                        color = TroveColors.Accent,
                    )
                    Text(
                        segment.text,
                        style = MaterialTheme.typography.bodySmall,
                        color = TroveColors.Ink.copy(alpha = 0.78f),
                        maxLines = 3,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            TextButton(onClick = onTranscript, modifier = Modifier.testTag("inline-transcript")) {
                Text("展开完整 transcript", style = MaterialTheme.typography.labelSmall)
            }
        }
        Spacer(Modifier.height(4.dp))
    }
}

private fun nextSpeed(speed: Float): Float {
    val speeds = listOf(1f, 1.25f, 1.5f, 2f)
    val index = speeds.indexOf(speed).takeIf { it >= 0 } ?: 0
    return speeds[(index + 1) % speeds.size]
}

private fun speedLabel(speed: Float): String =
    if (speed == speed.toInt().toFloat()) speed.toInt().toString() else speed.toString()

@Composable
private fun metaLine(item: LibraryItem): String = listOfNotNull(
    item.author,
    sourceTypeLabel(item.sourceType),
    platformLabel(item.platform),
).joinToString(" · ")

@Composable
private fun progressLine(item: LibraryItem): String {
    if (item.processingState == "failed") {
        return item.errorMessage?.take(60) ?: "处理失败"
    }
    if (item.isInbox) return processingLabel(item.processingState)
    return when (item.consumptionState) {
        "finished" -> if (item.isBookOnly) "已读完" else "已听完"
        "in_progress" -> {
            val pct = (progressFraction(item) * 100).roundToInt()
            if (item.isBookOnly) "$pct% 已读" else "$pct% 已听"
        }

        else -> "未开始"
    }
}

@Composable
private fun statusColor(item: LibraryItem): Color = when {
    item.processingState == "failed" -> TroveColors.Danger
    item.isInbox -> TroveColors.Cooking
    item.consumptionState == "finished" -> TroveColors.Green
    else -> TroveColors.Muted
}

private fun progressFraction(item: LibraryItem): Float {
    if (item.isBookOnly) {
        val locator = item.bookLocator ?: return 0f
        return runCatching {
            val json = org.json.JSONObject(locator)
            json.optDouble("epub_total_progression", Double.NaN)
                .takeIf { !it.isNaN() }
                ?: json.optDouble("scroll_ratio", 0.0)
        }.getOrDefault(0.0).toFloat().coerceIn(0f, 1f)
    }
    val duration = item.durationSec ?: return 0f
    if (duration <= 0) return 0f
    return (item.audioPositionSec / duration).toFloat().coerceIn(0f, 1f)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FilterDialog(
    state: LibraryUiState,
    onDismiss: () -> Unit,
    onType: (String?) -> Unit,
    onConsumption: (String?) -> Unit,
    onTag: (String?) -> Unit,
    onSource: (String?) -> Unit,
    onSort: (LibrarySort) -> Unit,
    onClear: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = TroveColors.Paper,
        title = {
            Text("筛选资料库", style = MaterialTheme.typography.titleLarge)
        },
        text = {
            Column(
                modifier = Modifier
                    .heightIn(max = 440.dp)
                    .verticalScroll(rememberScrollState())
                    .fillMaxWidth(),
            ) {
                Text("排序", style = MaterialTheme.typography.titleSmall)
                Row(
                    modifier = Modifier.padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    TroveChip(
                        "最近添加",
                        selected = state.sort == LibrarySort.RECENT_ADDED,
                        onClick = { onSort(LibrarySort.RECENT_ADDED) },
                    )
                    TroveChip(
                        "最近消费",
                        selected = state.sort == LibrarySort.RECENT_CONSUMED,
                        onClick = { onSort(LibrarySort.RECENT_CONSUMED) },
                    )
                }
                FilterSection(
                    title = stringResource(R.string.filter_type),
                    options = state.options.types,
                    selected = state.filters.type,
                    labelFor = { sourceTypeLabel(it) },
                    onSelect = onType,
                )
                FilterSection(
                    title = stringResource(R.string.filter_consumption),
                    options = state.options.consumptions,
                    selected = state.filters.consumption,
                    labelFor = { consumptionLabel(it) },
                    onSelect = onConsumption,
                )
                TagFilterSection(
                    options = state.options.tags,
                    selected = state.filters.tag,
                    onSelect = onTag,
                )
                FilterSection(
                    title = stringResource(R.string.filter_source),
                    options = state.options.sources,
                    selected = state.filters.source,
                    labelFor = { platformLabel(it) },
                    onSelect = onSource,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("关闭") }
        },
        dismissButton = {
            TextButton(onClick = onClear) { Text(stringResource(R.string.filter_clear)) }
        },
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FilterSection(
    title: String,
    options: List<String>,
    selected: String?,
    labelFor: @Composable (String) -> String,
    onSelect: (String?) -> Unit,
) {
    if (options.isEmpty()) return
    Text(
        title,
        style = MaterialTheme.typography.titleSmall,
        modifier = Modifier.padding(top = 10.dp),
    )
    FlowRow(
        modifier = Modifier.padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        options.forEach { option ->
            TroveChip(
                label = labelFor(option),
                selected = selected == option,
                onClick = { onSelect(if (selected == option) null else option) },
                modifier = Modifier.testTag("filter-option-$option"),
            )
        }
    }
}
