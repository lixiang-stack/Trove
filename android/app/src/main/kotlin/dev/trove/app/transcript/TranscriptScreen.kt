package dev.trove.app.transcript

import android.app.Activity
import androidx.activity.compose.LocalActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import dev.trove.app.ui.components.TroveRoundButton
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.transcript.TranscriptLoadResult
import dev.trove.core.transcript.TranscriptParser
import dev.trove.core.transcript.TranscriptSegment
import dev.trove.core.transcript.highlightRanges

@Composable
fun TranscriptScreen(
    state: TranscriptUiState,
    onBack: () -> Unit,
    onQuery: (String) -> Unit,
    onRetry: () -> Unit,
) {
    DarkSystemBars()
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(TroveColors.Player)
            .statusBarsPadding()
            .navigationBarsPadding()
            .testTag("transcript-screen"),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 10.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TroveRoundButton(
                icon = Icons.AutoMirrored.Filled.ArrowBack,
                contentDescription = "返回",
                onClick = onBack,
                contentColor = TroveColors.Paper,
                testTag = "transcript-back",
            )
            Text(
                "Transcript",
                style = MaterialTheme.typography.titleLarge,
                color = TroveColors.Paper,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
        OutlinedTextField(
            value = state.query,
            onValueChange = onQuery,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 10.dp)
                .testTag("transcript-search"),
            placeholder = {
                Text("搜索 transcript", color = TroveColors.Paper.copy(alpha = 0.38f))
            },
            singleLine = true,
            shape = RoundedCornerShape(14.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = TroveColors.Paper,
                unfocusedTextColor = TroveColors.Paper,
                focusedBorderColor = TroveColors.Accent,
                unfocusedBorderColor = Color.White.copy(alpha = 0.14f),
                cursorColor = TroveColors.Accent,
                focusedContainerColor = TroveColors.PlayerPanel,
                unfocusedContainerColor = TroveColors.PlayerPanel,
            ),
        )
        if (state.query.isNotBlank()) {
            Text(
                "${state.segments.size} 个匹配",
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Paper.copy(alpha = 0.5f),
                modifier = Modifier.padding(horizontal = 18.dp),
            )
        } else if (state.totalSegments > 0) {
            Text(
                "${state.totalSegments} 段",
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Paper.copy(alpha = 0.5f),
                modifier = Modifier.padding(horizontal = 18.dp),
            )
        }
        TranscriptBody(state = state, onRetry = onRetry)
    }
}

@Composable
private fun DarkSystemBars() {
    val view = LocalView.current
    val activity = LocalActivity.current
    DisposableEffect(view) {
        val controller = activity?.window?.let { WindowCompat.getInsetsController(it, view) }
        controller?.isAppearanceLightStatusBars = false
        controller?.isAppearanceLightNavigationBars = false
        onDispose {
            controller?.isAppearanceLightStatusBars = true
            controller?.isAppearanceLightNavigationBars = true
        }
    }
}

@Composable
private fun TranscriptBody(state: TranscriptUiState, onRetry: () -> Unit) {
    val item = state.item
    val transcriptArtifact = item?.transcriptArtifact
    val downloaded = transcriptArtifact?.downloadState == "completed"
    val message = when {
        state.loading -> null
        item == null -> "内容已不可用。"
        transcriptArtifact == null -> "这个 Item 没有 transcript。"
        state.loadResult == TranscriptLoadResult.Failed -> "transcript 解析失败，请重试或重新下载。"
        state.loadResult == TranscriptLoadResult.NotDownloaded && state.totalSegments == 0 ->
            "需要下载 transcript 才能离线阅读。"

        state.loadResult == TranscriptLoadResult.Empty -> "transcript 为空。"
        state.totalSegments == 0 && !downloaded -> "需要下载 transcript 才能离线阅读。"
        else -> null
    }
    if (state.loading) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = TroveColors.Accent, strokeWidth = 2.dp)
        }
        return
    }
    if (message != null) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                message,
                style = MaterialTheme.typography.bodyMedium,
                color = TroveColors.Paper.copy(alpha = 0.62f),
            )
            if (state.loadResult == TranscriptLoadResult.Failed) {
                Text(
                    "重试",
                    style = MaterialTheme.typography.labelLarge,
                    color = TroveColors.AccentSoft,
                    modifier = Modifier
                        .padding(top = 12.dp)
                        .clip(CircleShape)
                        .background(Color.White.copy(alpha = 0.06f))
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                        .testTag("transcript-retry")
                        .clickable(onClick = onRetry),
                )
            }
        }
        return
    }
    if (state.segments.isEmpty()) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text(
                "没有匹配的分段。",
                style = MaterialTheme.typography.bodyMedium,
                color = TroveColors.Paper.copy(alpha = 0.5f),
            )
        }
        return
    }
    LazyColumn(modifier = Modifier.fillMaxSize()) {
        items(state.segments, key = { it.seq }) { segment ->
            SegmentRow(segment = segment, query = state.query)
        }
    }
}

@Composable
private fun SegmentRow(segment: TranscriptSegment, query: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp, vertical = 10.dp)
            .testTag("transcript-segment-${segment.seq}"),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            TranscriptParser.timestamp(segment.startMs),
            style = MaterialTheme.typography.labelSmall,
            color = TroveColors.AccentSoft,
            modifier = Modifier.padding(top = 2.dp),
        )
        Text(
            text = highlighted(segment.text, query, TroveColors.Accent.copy(alpha = 0.45f)),
            style = MaterialTheme.typography.bodyMedium,
            color = TroveColors.Paper.copy(alpha = 0.85f),
            maxLines = 8,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

private fun highlighted(text: String, query: String, background: Color) = buildAnnotatedString {
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
