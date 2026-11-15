package dev.trove.app.search

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import dev.trove.app.library.consumptionLabel
import dev.trove.app.library.platformLabel
import dev.trove.app.library.sourceTypeLabel
import dev.trove.app.ui.components.RootTab
import dev.trove.app.ui.components.TroveBottomNav
import dev.trove.app.ui.components.TroveChip
import dev.trove.app.ui.components.TroveCover
import dev.trove.app.ui.components.TroveEmpty
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.library.LibraryItem
import dev.trove.core.search.SearchFilters
import dev.trove.core.transcript.highlightRanges

@Composable
fun SearchScreen(
    state: SearchUiState,
    libraryItems: List<LibraryItem>,
    onBack: () -> Unit,
    onQuery: (String) -> Unit,
    onFilters: (SearchFilters) -> Unit,
    onClearFilters: () -> Unit,
    onOpenItem: (String) -> Unit,
    onOpenTranscript: (String, Int, String) -> Unit,
    onOpenBook: (String, Int, Int?) -> Unit,
    onLibrary: () -> Unit,
    onAdd: () -> Unit,
) {
    var filterOpen by remember { mutableStateOf(false) }
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
                TextButton(
                    onClick = { filterOpen = true },
                    modifier = Modifier.testTag("search-filter"),
                ) {
                    Icon(
                        Icons.Filled.Tune,
                        contentDescription = null,
                        modifier = Modifier.size(15.dp),
                    )
                    Text("筛选", style = MaterialTheme.typography.labelSmall)
                }
            }
            SearchField(query = state.query, onQuery = onQuery)
            Text(
                text = when {
                    state.loading -> "正在搜索…"
                    state.error != null -> state.error
                    state.query.isBlank() -> "搜索标题、摘要、transcript、书文本和 Tag。"
                    state.localOnly -> "离线 · 仅搜索已下载内容 · ${state.results.size} 个 Item"
                    else -> "${state.results.size} 个 Item 命中「${state.query.trim()}」 · 按 Item 聚合"
                },
                style = MaterialTheme.typography.labelSmall,
                color = if (state.localOnly) TroveColors.Cooking else TroveColors.Muted,
                modifier = Modifier.padding(horizontal = 19.dp, vertical = 4.dp),
            )
            when {
                state.query.isBlank() -> TroveEmpty(
                    title = "搜全部内容",
                    copy = "输入两字中文词或英文关键词；在线搜索覆盖全库，离线只覆盖已下载 Item。",
                )

                state.hasSearched && !state.loading && state.results.isEmpty() &&
                    state.error == null -> TroveEmpty(
                    title = "没有命中",
                    copy = "试试两字中文词或英文关键词。",
                )

                else -> LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(
                        start = 18.dp,
                        end = 18.dp,
                        top = 8.dp,
                        bottom = 20.dp,
                    ),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(state.results, key = { it.item.id }) { result ->
                        SearchResultCard(
                            result = result,
                            query = state.query.trim(),
                            onClick = {
                                val anchor = result.evidence.firstOrNull()
                                when {
                                    anchor?.transcriptSeq != null -> onOpenTranscript(
                                        result.item.id,
                                        anchor.transcriptSeq,
                                        state.query.trim(),
                                    )

                                    anchor?.chapterIndex != null -> onOpenBook(
                                        result.item.id,
                                        anchor.chapterIndex,
                                        anchor.paragraphIndex,
                                    )

                                    else -> onOpenItem(result.item.id)
                                }
                            },
                        )
                    }
                }
            }
        }
    }
    if (filterOpen) {
        SearchFilterDialog(
            items = libraryItems,
            filters = state.filters,
            onDismiss = { filterOpen = false },
            onApply = {
                filterOpen = false
                onFilters(it)
            },
            onClear = {
                filterOpen = false
                onClearFilters()
            },
        )
    }
}

@Composable
private fun SearchField(query: String, onQuery: (String) -> Unit) {
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
            onValueChange = onQuery,
            modifier = Modifier
                .weight(1f)
                .padding(start = 6.dp)
                .testTag("search-input"),
            placeholder = { Text("搜标题、摘要、transcript、书、Tag", color = TroveColors.Muted) },
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
}

@Composable
private fun SearchResultCard(
    result: SearchUiResult,
    query: String,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(15.dp))
            .background(TroveColors.Paper2)
            .clickable(onClick = onClick)
            .padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(11.dp),
    ) {
        TroveCover(result.item, size = 46.dp)
        Column(modifier = Modifier.weight(1f)) {
            Text(
                result.item.title,
                style = MaterialTheme.typography.titleSmall,
                color = TroveColors.Ink,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                listOfNotNull(
                    result.item.author,
                    sourceTypeLabel(result.item.sourceType),
                    platformLabel(result.item.platform),
                    consumptionLabel(result.item.consumptionState),
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = TroveColors.Muted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            result.evidence.forEach { evidence ->
                Row(
                    modifier = Modifier.padding(top = 5.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(
                        evidence.label,
                        style = MaterialTheme.typography.labelSmall,
                        color = TroveColors.Accent,
                    )
                }
                Text(
                    highlightedText(evidence.snippet, query),
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Ink.copy(alpha = 0.72f),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            val summary = result.item.summary
            if (result.evidence.isEmpty() && summary != null) {
                Text(
                    summary,
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Ink.copy(alpha = 0.7f),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

private fun highlightedText(text: String, query: String) = buildAnnotatedString {
    val ranges = highlightRanges(text, query)
    if (ranges.isEmpty()) {
        append(text)
        return@buildAnnotatedString
    }
    var cursor = 0
    for (range in ranges) {
        if (range.first < cursor) continue
        append(text.substring(cursor, range.first))
        withStyle(SpanStyle(background = TroveColors.AccentSoft)) {
            append(text.substring(range.first, range.last + 1))
        }
        cursor = range.last + 1
    }
    append(text.substring(cursor))
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SearchFilterDialog(    items: List<LibraryItem>,
    filters: SearchFilters,
    onDismiss: () -> Unit,
    onApply: (SearchFilters) -> Unit,
    onClear: () -> Unit,
) {
    var draft by remember(filters) { mutableStateOf(filters) }
    val types = items.map { it.sourceType }.distinct().sorted()
    val consumptions = items.map { it.consumptionState }.distinct().sorted()
    val sources = items.map { it.platform }.filter { it.isNotBlank() }.distinct().sorted()
    val tags = items.flatMap { it.tags }.distinct().sortedBy { it.lowercase() }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = TroveColors.Paper,
        title = { Text("筛选搜索", style = MaterialTheme.typography.titleLarge) },
        text = {
            Column(
                modifier = Modifier
                    .verticalScroll(rememberScrollState())
                    .fillMaxWidth(),
            ) {
                SearchFilterSection(
                    title = "类型",
                    options = types,
                    selected = draft.type,
                    labelFor = { sourceTypeLabel(it) },
                    onSelect = { draft = draft.copy(type = it) },
                )
                SearchFilterSection(
                    title = "消费状态",
                    options = consumptions,
                    selected = draft.consumption,
                    labelFor = { consumptionLabel(it) },
                    onSelect = { draft = draft.copy(consumption = it) },
                )
                SearchFilterSection(
                    title = "Tag",
                    options = tags,
                    selected = draft.tag,
                    labelFor = { it },
                    onSelect = { draft = draft.copy(tag = it) },
                )
                SearchFilterSection(
                    title = "Source",
                    options = sources,
                    selected = draft.source,
                    labelFor = { platformLabel(it) },
                    onSelect = { draft = draft.copy(source = it) },
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onApply(draft) }) { Text("应用") }
        },
        dismissButton = {
            TextButton(onClick = onClear) { Text("清除筛选") }
        },
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SearchFilterSection(
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
            )
        }
    }
}
