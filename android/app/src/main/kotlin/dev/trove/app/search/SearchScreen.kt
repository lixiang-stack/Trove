package dev.trove.app.search

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import dev.trove.app.library.consumptionLabel
import dev.trove.app.library.platformLabel
import dev.trove.app.library.processingLabel
import dev.trove.app.library.sourceTypeLabel
import dev.trove.app.ui.components.RootTab
import dev.trove.app.ui.components.TroveBottomNav
import dev.trove.app.ui.components.TroveCover
import dev.trove.app.ui.components.TroveEmpty
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.library.LibraryItem

@Composable
fun SearchScreen(
    items: List<LibraryItem>,
    onBack: () -> Unit,
    onOpenItem: (String) -> Unit,
    onLibrary: () -> Unit,
    onAdd: () -> Unit,
) {
    Scaffold(
        modifier = Modifier.testTag("search-screen"),
        containerColor = TroveColors.Paper,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            TroveBottomNav(
                selected = RootTab.SEARCH,
                onSelect = {
                    when (it) {
                        RootTab.LIBRARY -> onLibrary()
                        RootTab.ADD -> onAdd()
                        RootTab.SEARCH -> Unit
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
                    "搜索",
                    style = MaterialTheme.typography.titleLarge,
                    color = TroveColors.Ink,
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
            SearchContent(items = items, onOpenItem = onOpenItem)
        }
    }
}

@Composable
fun SearchContent(
    items: List<LibraryItem>,
    onOpenItem: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var query by rememberSaveable { mutableStateOf("") }
    val normalized = query.trim()
    val results = if (normalized.isBlank()) {
        emptyList()
    } else {
        items.filter { item ->
            listOfNotNull(item.title, item.author, item.summary)
                .any { it.contains(normalized, ignoreCase = true) } ||
                item.tags.any { it.contains(normalized, ignoreCase = true) }
        }
    }
    Column(modifier = modifier.fillMaxSize()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 8.dp)
                .clip(RoundedCornerShape(14.dp))
                .background(TroveColors.Paper2)
                .padding(horizontal = 12.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Filled.Search,
                contentDescription = null,
                tint = TroveColors.Muted,
                modifier = Modifier.size(18.dp),
            )
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                modifier = Modifier
                    .weight(1f)
                    .padding(start = 6.dp)
                    .testTag("search-input"),
                placeholder = { Text("搜标题、摘要、Tag", color = TroveColors.Muted) },
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Color.Transparent,
                    unfocusedBorderColor = Color.Transparent,
                    focusedContainerColor = Color.Transparent,
                    unfocusedContainerColor = Color.Transparent,
                    focusedTextColor = TroveColors.Ink,
                    unfocusedTextColor = TroveColors.Ink,
                    cursorColor = TroveColors.Accent,
                ),
            )
        }
        Text(
            text = when {
                normalized.isBlank() -> "输入关键词；当前支持标题、摘要和 Tag，全文搜索将在后续接入。"
                results.isEmpty() -> "没有命中「$normalized」。"
                else -> "${results.size} 个 Item 命中「$normalized」 · 按 Item 聚合"
            },
            style = MaterialTheme.typography.labelSmall,
            color = TroveColors.Muted,
            modifier = Modifier.padding(horizontal = 19.dp, vertical = 4.dp),
        )
        if (normalized.isNotBlank() && results.isEmpty()) {
            TroveEmpty(
                title = "没有命中",
                copy = "试试标题、作者、摘要或 Tag 里的关键词。",
            )
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(
                    start = 18.dp,
                    end = 18.dp,
                    top = 8.dp,
                    bottom = 20.dp,
                ),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(results, key = { it.id }) { item ->
                    SearchResult(item = item, onClick = { onOpenItem(item.id) })
                }
            }
        }
    }
}

@Composable
private fun SearchResult(item: LibraryItem, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(15.dp))
            .background(TroveColors.Paper2)
            .clickable(onClick = onClick)
            .padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(11.dp),
    ) {
        TroveCover(item, size = 46.dp)
        Column(modifier = Modifier.weight(1f)) {
            Text(
                item.title,
                style = MaterialTheme.typography.titleSmall,
                color = TroveColors.Ink,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                listOfNotNull(
                    item.author,
                    sourceTypeLabel(item.sourceType),
                    platformLabel(item.platform),
                    consumptionLabel(item.consumptionState),
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            val summary = item.summary
            if (summary != null) {
                Text(
                    summary,
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Ink.copy(alpha = 0.7f),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(top = 2.dp),
                )
            }
            if (item.tags.isNotEmpty()) {
                Text(
                    item.tags.joinToString(" · ") { "#$it" },
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Accent,
                    modifier = Modifier.padding(top = 3.dp),
                )
            }
            if (item.isInbox) {
                Spacer(Modifier.size(2.dp))
                Text(
                    processingLabel(item.processingState),
                    style = MaterialTheme.typography.labelSmall,
                    color = TroveColors.Cooking,
                )
            }
        }
    }
}
