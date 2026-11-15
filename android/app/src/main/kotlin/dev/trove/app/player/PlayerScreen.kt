package dev.trove.app.player

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.LocalActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Article
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Done
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import dev.trove.app.R
import dev.trove.app.library.downloadErrorLabel
import dev.trove.app.library.downloadLabel
import dev.trove.app.library.platformLabel
import dev.trove.app.library.sourceTypeLabel
import dev.trove.app.ui.components.TroveCover
import dev.trove.app.ui.components.TrovePill
import dev.trove.app.ui.components.TroveRoundButton
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.library.LibraryItem
import dev.trove.core.transcript.TranscriptParser
import dev.trove.core.transcript.TranscriptSegment
import dev.trove.core.transcript.highlightRanges
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private val SPEEDS = listOf(1f, 1.25f, 1.5f, 2f)

private fun speedLabel(speed: Float): String =
    if (speed == speed.toInt().toFloat()) speed.toInt().toString() else speed.toString()

private fun nextSpeed(speed: Float): Float {
    val index = SPEEDS.indexOf(speed).takeIf { it >= 0 } ?: 0
    return SPEEDS[(index + 1) % SPEEDS.size]
}

@Composable
fun PlayerScreen(
    state: PlayerUiState,
    onBack: () -> Unit,
    onToggle: () -> Unit,
    onSeek: (Long) -> Unit,
    onSeekBy: (Long) -> Unit,
    onSpeed: (Float) -> Unit,
    onDownload: () -> Unit,
    onPauseDownload: () -> Unit,
    onRetryDownload: () -> Unit,
    onRemoveDownload: () -> Unit,
    onDelete: () -> Unit,
    onTranscript: () -> Unit,
    onRefreshTranscript: () -> Unit,
    onOpenDrawer: () -> Unit,
) {
    PlayerSystemBars()
    var confirmDelete by remember { mutableStateOf(false) }
    var menuOpen by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val notificationPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) {}
    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
    LaunchedEffect(state.deleted) {
        if (state.deleted) onBack()
    }
    LaunchedEffect(state.transcriptDownloaded, state.transcript.size) {
        if (state.transcriptDownloaded && state.transcript.isEmpty()) {
            onRefreshTranscript()
        }
    }
    val item = state.item
    Scaffold(
        modifier = Modifier
            .fillMaxSize()
            .testTag("player-screen"),
        containerColor = TroveColors.Player,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .statusBarsPadding()
                .navigationBarsPadding(),
        ) {
            PlayerTopBar(
                eyebrow = when {
                    item == null -> "资料库"
                    item.hasBook && !item.hasAudio -> "正在读"
                    else -> "正在听"
                },
                onBack = onBack,
                onDrawer = onOpenDrawer,
                menuOpen = menuOpen,
                onMenu = { menuOpen = !menuOpen },
                onDismissMenu = { menuOpen = false },
                item = item,
                onDownload = onDownload,
                onPauseDownload = onPauseDownload,
                onRetryDownload = onRetryDownload,
                onRemoveDownload = onRemoveDownload,
                onDelete = { confirmDelete = true },
            )
            when {
                state.loading -> Box(
                    Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) {
                    CircularProgressIndicator(color = TroveColors.Accent, strokeWidth = 2.dp)
                }

                item == null -> Column(
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        stringResource(R.string.player_missing),
                        color = TroveColors.Paper.copy(alpha = 0.6f),
                    )
                }

                else -> PlayerContent(
                    state = state,
                    onToggle = onToggle,
                    onSeek = onSeek,
                    onSeekBy = onSeekBy,
                    onSpeed = onSpeed,
                    onDownload = onDownload,
                    onRemoveDownload = onRemoveDownload,
                    onTranscript = onTranscript,
                    onRefreshTranscript = onRefreshTranscript,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 22.dp),
                )
            }
        }
    }
    if (confirmDelete) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            containerColor = TroveColors.Paper2,
            title = { Text(stringResource(R.string.player_delete)) },
            text = { Text(stringResource(R.string.player_delete_confirm)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmDelete = false
                        onDelete()
                    },
                ) {
                    Text(stringResource(R.string.player_delete_action))
                }
            },
            dismissButton = {
                TextButton(onClick = { confirmDelete = false }) {
                    Text(stringResource(R.string.player_cancel))
                }
            },
        )
    }
}

@Composable
private fun PlayerSystemBars() {
    val view = LocalView.current
    val activity = LocalActivity.current
    DisposableEffect(view) {
        val controller = activity?.window?.let {
            WindowCompat.getInsetsController(it, view)
        }
        controller?.isAppearanceLightStatusBars = false
        controller?.isAppearanceLightNavigationBars = false
        onDispose {
            controller?.isAppearanceLightStatusBars = true
            controller?.isAppearanceLightNavigationBars = true
        }
    }
}

@Composable
private fun PlayerTopBar(
    eyebrow: String,
    onBack: () -> Unit,
    onDrawer: () -> Unit,
    menuOpen: Boolean,
    onMenu: () -> Unit,
    onDismissMenu: () -> Unit,
    item: LibraryItem?,
    onDownload: () -> Unit,
    onPauseDownload: () -> Unit,
    onRetryDownload: () -> Unit,
    onRemoveDownload: () -> Unit,
    onDelete: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 10.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        TroveRoundButton(
            icon = Icons.AutoMirrored.Filled.ArrowBack,
            contentDescription = stringResource(R.string.player_back),
            onClick = onBack,
            size = 40.dp,
            contentColor = TroveColors.Paper,
            testTag = "player-back",
        )
        Text(
            eyebrow,
            style = MaterialTheme.typography.labelSmall,
            color = TroveColors.Paper.copy(alpha = 0.52f),
            textAlign = TextAlign.Center,
            modifier = Modifier.weight(1f),
        )
        Box {
            TroveRoundButton(
                icon = Icons.Filled.MoreVert,
                contentDescription = "更多",
                onClick = onMenu,
                size = 40.dp,
                contentColor = TroveColors.Paper,
            )
            DropdownMenu(expanded = menuOpen, onDismissRequest = onDismissMenu) {
                if (item != null) {
                    when (item.downloadState) {
                        "none", "partial" -> DropdownMenuItem(
                            text = { Text("下载 Item") },
                            onClick = {
                                onDismissMenu()
                                onDownload()
                            },
                        )

                        "downloading", "queued" -> DropdownMenuItem(
                            text = { Text("暂停下载") },
                            onClick = {
                                onDismissMenu()
                                onPauseDownload()
                            },
                        )

                        "failed", "paused" -> DropdownMenuItem(
                            text = { Text("重试下载") },
                            onClick = {
                                onDismissMenu()
                                onRetryDownload()
                            },
                        )

                        "completed" -> DropdownMenuItem(
                            text = { Text("移除下载") },
                            onClick = {
                                onDismissMenu()
                                onRemoveDownload()
                            },
                        )
                    }
                    DropdownMenuItem(
                        text = { Text("删除 Item") },
                        onClick = {
                            onDismissMenu()
                            onDelete()
                        },
                    )
                }
            }
        }
        TroveRoundButton(
            icon = Icons.AutoMirrored.Filled.List,
            contentDescription = "资料库菜单",
            onClick = onDrawer,
            size = 40.dp,
            contentColor = TroveColors.Paper,
        )
    }
}

@Composable
private fun PlayerContent(
    state: PlayerUiState,
    onToggle: () -> Unit,
    onSeek: (Long) -> Unit,
    onSeekBy: (Long) -> Unit,
    onSpeed: (Float) -> Unit,
    onDownload: () -> Unit,
    onRemoveDownload: () -> Unit,
    onTranscript: () -> Unit,
    onRefreshTranscript: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val item = state.item ?: return
    val playback = state.playback
    val isBook = item.hasBook && !item.hasAudio
    val isCurrent = playback.itemId == item.id
    val itemDuration = item.durationSec
    val durationMs = when {
        isCurrent && playback.durationMs > 0 -> playback.durationMs
        itemDuration != null -> (itemDuration * 1000).toLong()
        else -> 0L
    }
    val positionMs = if (isCurrent) playback.positionMs else (item.audioPositionSec * 1000).toLong()
    var transcriptOpen by rememberSaveable(item.id) { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val scrollState = rememberScrollState()
    Column(
        modifier = modifier
            .verticalScroll(scrollState)
            .padding(bottom = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.height(6.dp))
        TroveCover(item, size = 214.dp, corner = 22.dp)
        Text(
            item.title,
            style = MaterialTheme.typography.headlineMedium,
            color = TroveColors.Paper,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 20.dp),
        )
        Text(
            listOfNotNull(item.author, platformLabel(item.platform), sourceTypeLabel(item.sourceType))
                .joinToString(" · "),
            style = MaterialTheme.typography.bodySmall,
            color = TroveColors.Paper.copy(alpha = 0.58f),
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 7.dp),
        )
        if (item.tags.isNotEmpty()) {
            Row(
                modifier = Modifier.padding(top = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(5.dp),
            ) {
                item.tags.forEach { tag ->
                    TrovePill("#$tag", dark = true)
                }
            }
        }
        if (!isBook && (state.errorCode != null || playback.errorCode != null)) {
            PlayerError(state.errorCode ?: playback.errorCode.orEmpty())
        }
        if (isBook) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 24.dp)
                    .background(Color.White.copy(alpha = 0.05f), RoundedCornerShape(16.dp))
                    .padding(16.dp),
            ) {
                Text(
                    "EPUB 阅读",
                    style = MaterialTheme.typography.titleMedium,
                    color = TroveColors.Paper,
                )
                Text(
                    "Host 已保留 book.epub。Android Reader（Readium）将在下一阶段接入；当前可先下载，或在 Web Shell 阅读。",
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Paper.copy(alpha = 0.58f),
                    modifier = Modifier.padding(top = 6.dp),
                )
                val summary = item.summary
                if (summary != null) {
                    Text(
                        summary,
                        style = MaterialTheme.typography.bodyMedium,
                        color = TroveColors.Paper.copy(alpha = 0.78f),
                        modifier = Modifier.padding(top = 12.dp),
                    )
                }
            }
        }
        if (!isBook && durationMs > 0) {
            Column(modifier = Modifier.padding(top = 22.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(
                        TranscriptParser.timestamp(positionMs),
                        style = MaterialTheme.typography.labelSmall,
                        color = TroveColors.Paper.copy(alpha = 0.5f),
                    )
                    Text(
                        TranscriptParser.timestamp(durationMs),
                        style = MaterialTheme.typography.labelSmall,
                        color = TroveColors.Paper.copy(alpha = 0.5f),
                    )
                }
                PlayerSeekBar(
                    positionMs = positionMs,
                    durationMs = durationMs,
                    onSeek = onSeek,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 5.dp)
                        .testTag("player-slider"),
                )
            }
        }
        if (!isBook) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RoundTextButton("${speedLabel(playback.speed)}×") {
                    onSpeed(nextSpeed(playback.speed))
                }
                RoundTextButton("↺15") { onSeekBy(-15_000) }
                TroveRoundButton(
                    icon = if (isCurrent && playback.isPlaying) Icons.Filled.Pause else Icons.Filled.PlayArrow,
                    contentDescription = if (isCurrent && playback.isPlaying) "暂停" else "播放",
                    onClick = onToggle,
                    size = 62.dp,
                    iconSize = 26.dp,
                    background = TroveColors.Accent,
                    contentColor = TroveColors.White,
                    testTag = "player-toggle",
                )
                RoundTextButton("↻15") { onSeekBy(15_000) }
                TroveRoundButton(
                    icon = Icons.AutoMirrored.Filled.Article,
                    contentDescription = "Transcript",
                    onClick = {
                        transcriptOpen = true
                        scope.launch {
                            delay(60)
                            scrollState.animateScrollTo(scrollState.maxValue)
                        }
                    },
                    size = 40.dp,
                    contentColor = TroveColors.Paper,
                )
            }
        }
        DownloadPill(
            item = item,
            onDownload = onDownload,
            modifier = Modifier.padding(top = 8.dp),
        )
        if (!isBook) {
            TranscriptSection(
                item = item,
                state = state,
                open = transcriptOpen,
                onToggle = {
                    transcriptOpen = !transcriptOpen
                    if (transcriptOpen) {
                        scope.launch {
                            delay(60)
                            scrollState.animateScrollTo(scrollState.maxValue)
                        }
                    }
                },
                onFull = onTranscript,
                onRefresh = onRefreshTranscript,
            )
        }
    }
}

@Composable
private fun PlayerError(error: String) {
    Text(
        text = when (error) {
            "playback.no_audio" -> stringResource(R.string.player_no_audio)
            "playback.offline" -> stringResource(R.string.player_offline_no_download)
            "item.missing" -> stringResource(R.string.player_item_missing)
            "item.delete_failed" -> stringResource(R.string.player_delete_failed)
            "ERROR_CODE_IO_NETWORK_CONNECTION_FAILED",
            "ERROR_CODE_IO_NETWORK_CONNECTION_TIMEOUT" ->
                stringResource(R.string.player_error_network)

            "ERROR_CODE_IO_BAD_HTTP_STATUS" -> stringResource(R.string.player_error_http)
            "ERROR_CODE_DECODING_FAILED" -> stringResource(R.string.player_error_decoding)
            else -> stringResource(R.string.player_error)
        },
        color = TroveColors.AccentSoft,
        style = MaterialTheme.typography.bodySmall,
        textAlign = TextAlign.Center,
        modifier = Modifier
            .padding(top = 14.dp)
            .testTag("player-error"),
    )
}

@Composable
private fun RoundTextButton(label: String, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = Color.Transparent,
        contentColor = TroveColors.Paper,
        border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(alpha = 0.14f)),
    ) {
        Box(Modifier.size(40.dp), contentAlignment = Alignment.Center) {
            Text(label, style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun DownloadPill(
    item: LibraryItem,
    onDownload: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val label = downloadLabel(item.downloadState)
    val text = when (item.downloadState) {
        "none", "partial" -> "下载"
        "completed" -> "已下载 · 离线可用"
        else -> label ?: "下载"
    }
    Surface(
        onClick = {
            if (item.downloadState != "completed") onDownload()
        },
        shape = CircleShape,
        color = Color.White.copy(alpha = 0.06f),
        contentColor = TroveColors.Paper.copy(alpha = 0.76f),
        modifier = modifier,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                if (item.downloadState == "completed") Icons.Filled.Done else Icons.Filled.Download,
                contentDescription = null,
                modifier = Modifier.size(14.dp),
            )
            Spacer(Modifier.size(5.dp))
            Text(text, style = MaterialTheme.typography.labelSmall)
            val error = downloadErrorLabel(item)
            if (error != null) {
                Text(
                    " · $error",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.AccentSoft,
                )
            }
        }
    }
}

@Composable
private fun TranscriptSection(
    item: LibraryItem,
    state: PlayerUiState,
    open: Boolean,
    onToggle: () -> Unit,
    onFull: () -> Unit,
    onRefresh: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 26.dp)
            .background(Color.White.copy(alpha = 0.02f), RoundedCornerShape(16.dp))
            .padding(horizontal = 12.dp),
    ) {
        Surface(
            onClick = onToggle,
            color = Color.Transparent,
            contentColor = TroveColors.Paper,
            modifier = Modifier
                .fillMaxWidth()
                .testTag("player-transcript-open"),
        ) {
            Row(
                modifier = Modifier.padding(vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "Transcript",
                    style = MaterialTheme.typography.titleMedium,
                    color = TroveColors.Paper,
                )
                Text(
                    if (state.transcript.isEmpty()) " · 待下载" else " · ${state.transcript.size} 段 · 时间戳",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Paper.copy(alpha = 0.45f),
                    modifier = Modifier
                        .weight(1f)
                        .padding(start = 6.dp),
                )
                Icon(
                    if (open) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown,
                    contentDescription = null,
                    tint = TroveColors.Paper.copy(alpha = 0.55f),
                )
            }
        }
        when {
            state.transcript.isEmpty() && !state.transcriptDownloaded -> {
                Text(
                    stringResource(R.string.player_transcript_empty),
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Paper.copy(alpha = 0.5f),
                    modifier = Modifier.padding(bottom = 12.dp),
                )
                Text(
                    stringResource(R.string.player_transcript_download),
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Paper.copy(alpha = 0.4f),
                    modifier = Modifier.padding(bottom = 12.dp),
                )
            }

            state.transcript.isEmpty() -> {
                Text(
                    stringResource(R.string.player_transcript_parse),
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Paper.copy(alpha = 0.5f),
                    modifier = Modifier.padding(bottom = 12.dp),
                )
                Text(
                    "重新解析",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.AccentSoft,
                    modifier = Modifier
                        .clickable(onClick = onRefresh)
                        .padding(bottom = 12.dp),
                )
            }

            open -> {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 380.dp),
                ) {
                    items(state.transcript, key = { it.seq }) { segment ->
                        SegmentRow(segment = segment, query = "")
                    }
                }
                TextButton(
                    onClick = onFull,
                    modifier = Modifier.testTag("player-transcript-full"),
                ) {
                    Text("展开完整 transcript", color = TroveColors.AccentSoft)
                }
            }

            else -> {
                Text(
                    state.transcript.first().text,
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Paper.copy(alpha = 0.55f),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(bottom = 12.dp),
                )
            }
        }
    }
}

@Composable
private fun SegmentRow(segment: TranscriptSegment, query: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(
            TranscriptParser.timestamp(segment.startMs),
            style = MaterialTheme.typography.labelSmall,
            color = TroveColors.AccentSoft,
        )
        Text(
            text = highlighted(segment.text, query, TroveColors.Accent.copy(alpha = 0.45f)),
            style = MaterialTheme.typography.bodySmall,
            color = TroveColors.Paper.copy(alpha = 0.82f),
        )
    }
}

fun highlighted(text: String, query: String, background: Color) = buildAnnotatedString {
    val ranges = highlightRanges(text, query)
    if (ranges.isEmpty()) {
        append(text)
        return@buildAnnotatedString
    }
    var cursor = 0
    for (range in ranges) {
        append(text.substring(cursor, range.first))
        withStyle(SpanStyle(background = background)) {
            append(text.substring(range.first, range.last + 1))
        }
        cursor = range.last + 1
    }
    append(text.substring(cursor))
}

@Composable
private fun PlayerSeekBar(
    positionMs: Long,
    durationMs: Long,
    onSeek: (Long) -> Unit,
    modifier: Modifier = Modifier,
) {
    var width by remember { mutableStateOf(1) }
    var dragging by remember { mutableStateOf<Float?>(null) }
    val fraction = dragging ?: (positionMs.toFloat() / durationMs.coerceAtLeast(1)).coerceIn(0f, 1f)
    Box(
        modifier = modifier
            .height(26.dp)
            .onSizeChanged { width = it.width.coerceAtLeast(1) }
            .pointerInput(width) {
                detectTapGestures { offset ->
                    onSeek(((offset.x / width) * durationMs).toLong())
                }
            }
            .pointerInput(width) {
                detectHorizontalDragGestures(
                    onDragStart = { offset ->
                        dragging = (offset.x / width).coerceIn(0f, 1f)
                    },
                    onDragEnd = {
                        dragging?.let { onSeek((it * durationMs).toLong()) }
                        dragging = null
                    },
                ) { change, _ ->
                    dragging = (change.position.x / width).coerceIn(0f, 1f)
                }
            },
        contentAlignment = Alignment.CenterStart,
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(3.dp)
                .clip(CircleShape)
                .background(Color.White.copy(alpha = 0.14f)),
        )
        Box(
            Modifier
                .fillMaxWidth(fraction)
                .height(3.dp)
                .clip(CircleShape)
                .background(TroveColors.Accent),
        )
    }
}
