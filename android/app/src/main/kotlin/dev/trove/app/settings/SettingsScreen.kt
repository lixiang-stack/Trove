package dev.trove.app.settings

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dev.trove.app.library.formatBytes
import dev.trove.app.ui.components.TroveChip
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.download.DEFAULT_QUOTA_BYTES

@Composable
fun SettingsScreen(
    viewModel: SettingsViewModel,
    onBack: () -> Unit,
    onDownloads: () -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var confirmClear by remember { mutableStateOf(false) }
    var notificationsEnabled by remember { mutableStateOf(notificationsAllowed(context)) }
    var batteryIgnored by remember { mutableStateOf(batteryOptimizationIgnored(context)) }
    val notificationPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { notificationsEnabled = notificationsAllowed(context) }
    LifecycleResumeEffect(Unit) {
        notificationsEnabled = notificationsAllowed(context)
        batteryIgnored = batteryOptimizationIgnored(context)
        viewModel.refresh()
        onPauseOrDispose { }
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(TroveColors.Paper)
            .statusBarsPadding()
            .navigationBarsPadding()
            .testTag("settings-screen"),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                onClick = onBack,
                shape = CircleShape,
                color = Color.Transparent,
                contentColor = TroveColors.Ink,
            ) {
                Box(Modifier.size(42.dp), contentAlignment = Alignment.Center) {
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = "返回",
                        modifier = Modifier.size(20.dp),
                    )
                }
            }
            Text(
                "设置",
                style = MaterialTheme.typography.titleLarge,
                color = TroveColors.Ink,
                modifier = Modifier.padding(start = 6.dp),
            )
        }
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 18.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            val message = state.message
            if (message != null) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(TroveColors.AccentSoft.copy(alpha = 0.35f), RoundedCornerShape(10.dp))
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        message,
                        style = MaterialTheme.typography.labelSmall,
                        color = TroveColors.Ink,
                        modifier = Modifier.weight(1f),
                    )
                    TextButton(onClick = viewModel::dismissMessage) { Text("知道了") }
                }
            }
            SettingsSection(title = "Host") {
                SettingsRow(label = "地址", value = state.hostUrl.ifBlank { "未连接" })
                SettingsRow(label = "设备", value = state.deviceName.ifBlank { "未知" })
                SettingsRow(
                    label = "设备 ID",
                    value = state.deviceId.take(12).ifBlank { "未知" },
                )
                SettingsRow(label = "API 版本", value = state.diagnostics.apiVersion)
            }
            SettingsSection(title = "同步") {
                SettingsRow(
                    label = "状态",
                    value = when {
                        state.syncing -> "正在同步"
                        state.offline -> "离线"
                        state.syncErrorCode != null -> "失败（${state.syncErrorCode}）"
                        else -> "空闲"
                    },
                )
                SettingsRow(
                    label = "上次成功",
                    value = state.lastSuccessAt?.let { formatTime(it) } ?: "尚未同步",
                )
                SettingsToggle(
                    label = "周期同步",
                    checked = state.syncPreferences.periodicEnabled,
                    onChange = viewModel::setPeriodicEnabled,
                )
                if (state.syncPreferences.periodicEnabled) {
                    Text("同步间隔（分钟）", style = MaterialTheme.typography.labelMedium, color = TroveColors.Muted)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf(15L, 30L, 60L, 120L).forEach { interval ->
                            TroveChip(
                                label = interval.toString(),
                                selected = state.syncPreferences.intervalMinutes == interval,
                                onClick = { viewModel.setIntervalMinutes(interval) },
                            )
                        }
                    }
                }
                OutlinedButton(
                    onClick = viewModel::syncNow,
                    enabled = !state.syncing,
                    modifier = Modifier.testTag("settings-sync-now"),
                ) {
                    Text(if (state.syncing) "正在同步…" else "立即同步")
                }
                SettingsRow(
                    label = "Cursor",
                    value = listOfNotNull(
                        state.storage.contentCursor?.let { "content ${it.take(12)}" },
                        state.storage.stateCursor?.let { "state ${it.take(12)}" },
                    ).joinToString(" · ").ifBlank { "未建立" },
                )
            }
            SettingsSection(title = "下载与存储") {
                SettingsRow(
                    label = "已下载",
                    value = "${formatBytes(state.storage.downloadedBytes)} / ${formatBytes(state.storage.quotaBytes)}",
                )
                SettingsRow(
                    label = "手机剩余",
                    value = formatBytes(state.storage.availableBytes),
                )
                SettingsRow(label = "下载队列", value = "${state.storage.downloadQueue} 个 Item")
                SettingsToggle(
                    label = "允许移动网络下载",
                    checked = state.downloadPreferences.allowMetered,
                    onChange = viewModel::setAllowMetered,
                )
                SettingsToggle(
                    label = "仅充电时下载",
                    checked = state.downloadPreferences.chargingOnly,
                    onChange = viewModel::setChargingOnly,
                )
                Text("存储配额", style = MaterialTheme.typography.labelMedium, color = TroveColors.Muted)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf(
                        2L * 1024 * 1024 * 1024,
                        DEFAULT_QUOTA_BYTES,
                        10L * 1024 * 1024 * 1024,
                    ).forEach { bytes ->
                        TroveChip(
                            label = formatBytes(bytes),
                            selected = state.storage.quotaBytes == bytes,
                            onClick = { viewModel.setQuotaBytes(bytes) },
                        )
                    }
                }
                OutlinedButton(onClick = onDownloads, modifier = Modifier.testTag("settings-downloads")) {
                    Text("打开下载管理")
                }
            }
            SettingsSection(title = "平台") {
                SettingsRow(
                    label = "通知权限",
                    value = if (notificationsEnabled) "已允许" else "未允许",
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (!notificationsEnabled && Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        TextButton(
                            onClick = {
                                notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                            },
                        ) { Text("请求权限") }
                    }
                    TextButton(
                        onClick = {
                            context.startActivity(
                                Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                                    .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
                            )
                        },
                    ) { Text("通知设置") }
                }
                SettingsRow(
                    label = "电池优化",
                    value = if (batteryIgnored) "已忽略" else "受系统限制",
                )
                TextButton(
                    onClick = {
                        context.startActivity(
                            Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
                        )
                    },
                ) { Text("打开电池优化设置") }
            }
            SettingsSection(title = "诊断") {
                SettingsRow(label = "Host", value = maskHost(state.hostUrl))
                SettingsRow(
                    label = "能力",
                    value = state.diagnostics.capabilities.joinToString(", ").ifBlank { "未知" },
                )
                SettingsRow(
                    label = "同步错误",
                    value = state.diagnostics.errorCode ?: "无",
                )
                SettingsRow(
                    label = "Epoch",
                    value = state.storage.epoch?.take(12) ?: "未知",
                )
                OutlinedButton(
                    onClick = viewModel::rebuildSearchIndex,
                    modifier = Modifier.testTag("settings-rebuild-search"),
                ) {
                    Text("重建搜索索引")
                }
                Text(
                    "诊断信息只包含同步/下载状态，不包含 token、密码、Cookie 或完整文件路径。",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                )
            }
            SettingsSection(title = "账号与本地数据") {
                TextButton(onClick = viewModel::signOut) { Text("退出登录") }
                Text(
                    "退出登录不会删除已下载内容；下次登录后仍可离线使用。",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                )
                TextButton(
                    onClick = { confirmClear = true },
                    enabled = !state.clearing,
                    modifier = Modifier.testTag("settings-clear"),
                ) {
                    Text(if (state.clearing) "正在清除…" else "清除本地数据", color = TroveColors.Danger)
                }
                Text(
                    "清除会删除本地数据库、搜索索引和所有下载；Host 上的 Item 不受影响。",
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Muted,
                )
            }
            if (state.clearing) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        color = TroveColors.Accent,
                        strokeWidth = 2.dp,
                    )
                    Text("正在清除本地数据…", style = MaterialTheme.typography.labelSmall)
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
    if (confirmClear) {
        AlertDialog(
            onDismissRequest = { confirmClear = false },
            containerColor = TroveColors.Paper2,
            title = { Text("清除本地数据") },
            text = { Text("将删除所有下载、本地数据库和搜索索引。Host 上的 Item 不受影响。") },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmClear = false
                        viewModel.clearLocalData()
                    },
                ) { Text("清除", color = TroveColors.Danger) }
            },
            dismissButton = {
                TextButton(onClick = { confirmClear = false }) { Text("取消") }
            },
        )
    }
}

@Composable
private fun SettingsSection(title: String, content: @Composable () -> Unit) {
    Surface(
        shape = RoundedCornerShape(14.dp),
        color = TroveColors.Paper2,
        border = androidx.compose.foundation.BorderStroke(1.dp, TroveColors.Line),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                title,
                style = MaterialTheme.typography.titleSmall,
                color = TroveColors.Ink,
            )
            HorizontalDivider(color = TroveColors.Line, modifier = Modifier.padding(bottom = 2.dp))
            content()
        }
    }
}

@Composable
private fun SettingsRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            color = TroveColors.Muted,
            modifier = Modifier.weight(1f),
        )
        Text(
            value,
            style = MaterialTheme.typography.labelSmall,
            color = TroveColors.Ink,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun SettingsToggle(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            color = TroveColors.Ink,
            modifier = Modifier.weight(1f),
        )
        Switch(
            checked = checked,
            onCheckedChange = onChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = TroveColors.White,
                checkedTrackColor = TroveColors.Accent,
                uncheckedThumbColor = TroveColors.Muted,
                uncheckedTrackColor = TroveColors.Line,
                uncheckedBorderColor = TroveColors.Line,
            ),
        )
    }
}

private fun notificationsAllowed(context: android.content.Context): Boolean =
    Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
        ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED

private fun batteryOptimizationIgnored(context: android.content.Context): Boolean {
    val power = context.getSystemService(PowerManager::class.java) ?: return false
    return power.isIgnoringBatteryOptimizations(context.packageName)
}

private fun formatTime(timestamp: Long): String {
    val formatter = java.text.SimpleDateFormat("MM-dd HH:mm", java.util.Locale.getDefault())
    return formatter.format(java.util.Date(timestamp))
}

internal fun maskHost(host: String): String {
    if (host.isBlank()) return "未连接"
    val scheme = host.substringBefore("://", "")
    val rest = host.substringAfter("://", host)
    val authority = rest.substringBefore('/')
    val visible = authority.take(3)
    val masked = "$visible***"
    return if (scheme.isEmpty()) masked else "$scheme://$masked"
}
