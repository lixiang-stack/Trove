package dev.trove.app.download

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
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
import androidx.compose.ui.unit.dp
import dev.trove.app.library.LibraryUiState
import dev.trove.app.library.downloadErrorLabel
import dev.trove.app.library.downloadLabel
import dev.trove.app.library.formatBytes
import dev.trove.app.ui.components.TinyProgress
import dev.trove.app.ui.components.TroveCover
import dev.trove.app.ui.components.TroveEmpty
import dev.trove.app.ui.components.TroveRoundButton
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.download.DEFAULT_QUOTA_BYTES
import dev.trove.core.library.LibraryItem

@Composable
fun DownloadsScreen(
    state: LibraryUiState,
    onBack: () -> Unit,
    onPause: (String) -> Unit,
    onRetry: (String) -> Unit,
    onRemove: (String) -> Unit,
    onAllowMetered: (Boolean) -> Unit,
    onChargingOnly: (Boolean) -> Unit,
    onQuota: (Long) -> Unit,
) {
    var quotaOpen by remember { mutableStateOf(false) }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(TroveColors.Paper)
            .statusBarsPadding()
            .navigationBarsPadding(),
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
                testTag = "downloads-back",
            )
            Text(
                "下载",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp)
                .verticalScroll(rememberScrollState()),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text("允许移动网络下载", style = MaterialTheme.typography.bodyMedium)
                    Text("仅充电时下载", style = MaterialTheme.typography.bodyMedium)
                }
                Column {
                    Switch(
                        checked = state.downloadPreferences.allowMetered,
                        onCheckedChange = onAllowMetered,
                        colors = switchColors(),
                    )
                    Switch(
                        checked = state.downloadPreferences.chargingOnly,
                        onCheckedChange = onChargingOnly,
                        colors = switchColors(),
                    )
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "配额 ${formatBytes(state.downloadPreferences.quotaBytes)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                    modifier = Modifier.weight(1f),
                )
                TextButton(
                    onClick = { quotaOpen = true },
                    modifier = Modifier.testTag("downloads-quota"),
                ) {
                    Text("调整配额", style = MaterialTheme.typography.labelSmall)
                }
            }
            Text(
                "移除下载只删除手机上的文件，不会删除 Host 上的 Item。",
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
            )
            HorizontalDivider(color = TroveColors.Line, modifier = Modifier.padding(vertical = 10.dp))
            if (state.downloads.isEmpty()) {
                TroveEmpty(
                    title = "还没有下载",
                    copy = "在 Item 页面选择下载，即可离线播放和阅读。",
                )
            } else {
                state.downloads.forEach { item ->
                    DownloadRow(
                        item = item,
                        onPause = { onPause(item.id) },
                        onRetry = { onRetry(item.id) },
                        onRemove = { onRemove(item.id) },
                    )
                    HorizontalDivider(color = TroveColors.Line)
                }
            }
        }
    }
    if (quotaOpen) {
        AlertDialog(
            onDismissRequest = { quotaOpen = false },
            containerColor = TroveColors.Paper2,
            title = { Text("调整配额") },
            text = {
                Column {
                    listOf(
                        2L * 1024 * 1024 * 1024 to "2 GB",
                        DEFAULT_QUOTA_BYTES to "5 GB",
                        10L * 1024 * 1024 * 1024 to "10 GB",
                    ).forEach { (bytes, label) ->
                        TextButton(
                            onClick = {
                                onQuota(bytes)
                                quotaOpen = false
                            },
                        ) {
                            Text(label)
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { quotaOpen = false }) { Text("关闭") }
            },
        )
    }
}

@Composable
private fun switchColors() = SwitchDefaults.colors(
    checkedThumbColor = TroveColors.White,
    checkedTrackColor = TroveColors.Accent,
    uncheckedThumbColor = TroveColors.Muted,
    uncheckedTrackColor = TroveColors.Line,
    uncheckedBorderColor = TroveColors.Line,
)

@Composable
private fun DownloadRow(
    item: LibraryItem,
    onPause: () -> Unit,
    onRetry: () -> Unit,
    onRemove: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        TroveCover(item, size = 48.dp)
        Column(modifier = Modifier.weight(1f)) {
            Text(item.title, style = MaterialTheme.typography.titleSmall)
            val label = downloadLabel(item.downloadState)
            if (label != null) {
                Text(
                    "${(item.downloadProgress * 100).toInt()}% · $label",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                )
            }
            val error = downloadErrorLabel(item)
            if (error != null) {
                Text(
                    error,
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Danger,
                )
            }
            if (item.downloadState == "downloading" || item.downloadState == "queued") {
                TinyProgress(
                    fraction = item.downloadProgress,
                    modifier = Modifier.padding(top = 6.dp),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                when (item.downloadState) {
                    "downloading", "queued" -> TextButton(onClick = onPause) {
                        Text("暂停")
                    }

                    "failed", "paused" -> TextButton(onClick = onRetry) {
                        Text("重试")
                    }
                }
                TextButton(onClick = onRemove) { Text("移除下载") }
            }
        }
    }
}
