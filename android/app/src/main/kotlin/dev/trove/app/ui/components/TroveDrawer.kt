package dev.trove.app.ui.components

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import dev.trove.app.library.LibraryFilters
import dev.trove.app.library.LibrarySort
import dev.trove.app.library.LibraryUiState
import dev.trove.app.library.processingLabel
import dev.trove.app.library.sourceTypeLabel
import dev.trove.app.search.SearchContent
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.library.LibraryItem

enum class DrawerTab(val label: String) {
    LIBRARY("资料库"),
    SEARCH("搜索"),
    ADD("添加"),
}

@Composable
fun TroveDrawer(
    open: Boolean,
    tab: DrawerTab,
    state: LibraryUiState,
    onTab: (DrawerTab) -> Unit,
    onClose: () -> Unit,
    onOpenItem: (String) -> Unit,
    onInbox: (Boolean) -> Unit,
    onConsumption: (String?) -> Unit,
    onAdd: () -> Unit,
    onDownloads: () -> Unit,
    onDevices: () -> Unit,
    onSignOut: () -> Unit,
) {
    if (!open) return
    BackHandler(onBack = onClose)
    Box(modifier = Modifier.fillMaxSize()) {
        Box(
            Modifier
                .fillMaxSize()
                .background(Color.Black.copy(alpha = 0.52f))
                .clickable(onClick = onClose),
        )
        Column(
            modifier = Modifier
                .fillMaxHeight()
                .fillMaxWidth(0.88f)
                .background(TroveColors.Paper)
                .statusBarsPadding()
                .testTag("trove-drawer"),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(start = 18.dp, end = 8.dp, top = 12.dp, bottom = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "资料库",
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.weight(1f),
                )
                Surface(
                    onClick = onClose,
                    color = Color.Transparent,
                    contentColor = TroveColors.Ink,
                    modifier = Modifier.padding(4.dp),
                ) {
                    Icon(Icons.Filled.Close, contentDescription = "关闭", modifier = Modifier.padding(8.dp))
                }
            }
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                DrawerTab.entries.forEach { item ->
                    val active = item == tab
                    Column(
                        modifier = Modifier
                            .clickable { onTab(item) }
                            .padding(horizontal = 10.dp, vertical = 8.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            item.label,
                            style = MaterialTheme.typography.labelLarge,
                            color = if (active) TroveColors.Ink else TroveColors.Muted,
                        )
                        Box(
                            Modifier
                                .padding(top = 5.dp)
                                .width(28.dp)
                                .height(3.dp)
                                .background(
                                    if (active) TroveColors.Accent else Color.Transparent,
                                    RoundedCornerShape(99.dp),
                                ),
                        )
                    }
                }
            }
            HorizontalDivider(color = TroveColors.Line)
            when (tab) {
                DrawerTab.LIBRARY -> DrawerLibrary(
                    state = state,
                    onOpenItem = onOpenItem,
                    onInbox = onInbox,
                    onConsumption = onConsumption,
                    onAdd = onAdd,
                    modifier = Modifier.weight(1f),
                )

                DrawerTab.SEARCH -> SearchContent(
                    items = state.allItems,
                    onOpenItem = onOpenItem,
                    modifier = Modifier.weight(1f),
                )

                DrawerTab.ADD -> DrawerAdd(onAdd = onAdd, modifier = Modifier.weight(1f))
            }
            HorizontalDivider(color = TroveColors.Line)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 8.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                TextButton(onClick = onDownloads) { Text("下载") }
                TextButton(onClick = onDevices) { Text("设备") }
                TextButton(onClick = onSignOut) { Text("退出登录") }
            }
        }
    }
}

@Composable
private fun DrawerLibrary(
    state: LibraryUiState,
    onOpenItem: (String) -> Unit,
    onInbox: (Boolean) -> Unit,
    onConsumption: (String?) -> Unit,
    onAdd: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val filters = state.filters
    val selected = when {
        filters.inbox -> "processing"
        filters.consumption == "in_progress" -> "in_progress"
        filters.consumption == "finished" -> "finished"
        else -> "all"
    }
    Column(modifier = modifier) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 14.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            listOf(
                "all" to "全部",
                "in_progress" to "进行中",
                "processing" to "处理中",
                "finished" to "已完成",
            ).forEach { (key, label) ->
                TroveChip(
                    label = label,
                    selected = selected == key,
                    onClick = {
                        when (key) {
                            "all" -> {
                                onInbox(false)
                                onConsumption(null)
                            }

                            "in_progress" -> {
                                onInbox(false)
                                onConsumption("in_progress")
                            }

                            "processing" -> {
                                onInbox(true)
                                onConsumption(null)
                            }

                            "finished" -> {
                                onInbox(false)
                                onConsumption("finished")
                            }
                        }
                    },
                )
            }
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                "${state.items.size} 条",
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
                modifier = Modifier.weight(1f),
            )
            Text(
                if (state.sort == LibrarySort.RECENT_ADDED) "最近添加" else "最近消费",
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
            )
        }
        LazyColumn(modifier = Modifier.fillMaxSize()) {
            items(state.items, key = { it.id }) { item ->
                DrawerRow(item = item, onClick = { onOpenItem(item.id) })
            }
            if (state.items.isEmpty()) {
                item {
                    TroveEmpty(
                        title = "库还是空的",
                        copy = "从链接、文件或播客 feed 开始。",
                        action = "添加",
                        onAction = onAdd,
                    )
                }
            }
        }
    }
}

@Composable
private fun DrawerRow(item: LibraryItem, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        TroveCover(item, size = 44.dp)
        Column(modifier = Modifier.weight(1f)) {
            Text(
                item.title,
                style = MaterialTheme.typography.titleSmall,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                listOfNotNull(item.author, sourceTypeLabel(item.sourceType))
                    .joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (item.isInbox) {
                Text(
                    processingLabel(item.processingState),
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Cooking,
                )
            }
        }
    }
}

@Composable
private fun DrawerAdd(onAdd: () -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("添加内容", style = MaterialTheme.typography.titleLarge)
        Text(
            "Android 端 Add 尚未接入 Host。当前请先在 Host Console 添加链接、文件或播客单集，Library 会自动同步。",
            style = MaterialTheme.typography.bodyMedium,
            color = TroveColors.Muted,
        )
        Surface(
            onClick = onAdd,
            shape = RoundedCornerShape(12.dp),
            color = TroveColors.Paper2,
            border = androidx.compose.foundation.BorderStroke(1.dp, TroveColors.Line),
        ) {
            Text(
                "打开添加页",
                style = MaterialTheme.typography.labelLarge,
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            )
        }
    }
}
