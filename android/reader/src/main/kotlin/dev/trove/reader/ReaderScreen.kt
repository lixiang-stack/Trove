package dev.trove.reader

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.TextFields
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Slider
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.fragment.app.FragmentContainerView
import dev.trove.core.db.BookChapterEntity

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReaderScreen(
    state: ReaderUiState,
    onBack: () -> Unit,
    onChapter: (Int) -> Unit,
    onSearchOpen: () -> Unit,
    onSearchClose: () -> Unit,
    onSearchQuery: (String) -> Unit,
    onSearchResult: (ReaderSearchMatch) -> Unit,
    onSettings: (ReaderTextSettings) -> Unit,
    onToggleFinished: () -> Unit,
    onReaderContainer: () -> Unit,
) {
    var tocOpen by remember { mutableStateOf(false) }
    var settingsOpen by remember { mutableStateOf(false) }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(ReaderColors.Paper)
            .statusBarsPadding()
            .navigationBarsPadding(),
    ) {
        ReaderTopBar(
            state = state,
            onBack = onBack,
            onToc = { tocOpen = true },
            onSearch = onSearchOpen,
            onSettings = { settingsOpen = true },
            onToggleFinished = onToggleFinished,
        )
        when {
            state.loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = ReaderColors.Accent, strokeWidth = 2.dp)
            }

            state.errorCode != null -> ReaderError(state.errorCode)
            else -> Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(top = 2.dp)
                    .testTag("reader-container"),
            ) {
                AndroidView(
                    factory = { context ->
                        FragmentContainerView(context).apply {
                            id = R.id.reader_container
                            post { onReaderContainer() }
                        }
                    },
                    modifier = Modifier.fillMaxSize(),
                )
                ReaderProgress(state)
            }
        }
    }
    if (tocOpen) {
        ModalBottomSheet(
            onDismissRequest = { tocOpen = false },
            containerColor = ReaderColors.Paper2,
        ) {
            Text(
                "章节",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
            )
            if (state.chapters.isEmpty()) {
                Text(
                    "这本书没有可用的章节信息。",
                    color = ReaderColors.Muted,
                    modifier = Modifier.padding(20.dp),
                )
            } else {
                LazyColumn(modifier = Modifier.heightIn(max = 420.dp)) {
                    items(state.chapters, key = { it.chapterIndex }) { chapter ->
                        ChapterRow(
                            chapter = chapter,
                            selected = chapter.chapterIndex == state.currentChapter,
                            onClick = {
                                tocOpen = false
                                onChapter(chapter.chapterIndex)
                            },
                        )
                    }
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
    if (settingsOpen) {
        ModalBottomSheet(
            onDismissRequest = { settingsOpen = false },
            containerColor = ReaderColors.Paper2,
        ) {
            ReaderSettings(
                settings = state.textSettings,
                onChange = onSettings,
            )
            Spacer(Modifier.height(24.dp))
        }
    }
    if (state.searchOpen) {
        ModalBottomSheet(
            onDismissRequest = onSearchClose,
            containerColor = ReaderColors.Paper2,
        ) {
            SearchSheet(state = state, onQuery = onSearchQuery, onResult = onSearchResult)
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun ReaderTopBar(
    state: ReaderUiState,
    onBack: () -> Unit,
    onToc: () -> Unit,
    onSearch: () -> Unit,
    onSettings: () -> Unit,
    onToggleFinished: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(ReaderColors.Paper2)
            .padding(horizontal = 6.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        ReaderIconButton(Icons.AutoMirrored.Filled.ArrowBack, "返回", onBack)
        Column(modifier = Modifier.weight(1f)) {
            Text(
                state.title.ifBlank { "阅读" },
                style = MaterialTheme.typography.titleMedium,
                color = ReaderColors.Ink,
                maxLines = 1,
            )
            Text(
                buildString {
                    append("${(state.progress * 100).toInt()}%")
                    if (state.chapters.isNotEmpty()) {
                        append(" · 第 ${state.currentChapter + 1}/${state.chapters.size} 章")
                    }
                    if (state.finished) append(" · 已完成")
                },
                style = MaterialTheme.typography.labelSmall,
                color = ReaderColors.Muted,
            )
        }
        ReaderIconButton(
            if (state.finished) Icons.Filled.CheckCircle else Icons.Filled.RadioButtonUnchecked,
            if (state.finished) "标记未完成" else "标记完成",
            onToggleFinished,
        )
        ReaderIconButton(Icons.AutoMirrored.Filled.List, "章节", onToc)
        ReaderIconButton(Icons.Filled.Search, "书内搜索", onSearch)
        ReaderIconButton(Icons.Filled.TextFields, "阅读设置", onSettings)
    }
}

@Composable
private fun ReaderIconButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    description: String,
    onClick: () -> Unit,
) {
    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = Color.Transparent,
        contentColor = ReaderColors.Ink,
    ) {
        Box(Modifier.size(48.dp), contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = description, modifier = Modifier.size(20.dp))
        }
    }
}

@Composable
private fun ReaderProgress(state: ReaderUiState) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(2.dp)
            .background(ReaderColors.Line),
    ) {
        Box(
            Modifier
                .fillMaxWidth(state.progress.toFloat().coerceIn(0f, 1f))
                .height(2.dp)
                .background(ReaderColors.Accent),
        )
    }
}

@Composable
private fun ReaderError(code: String) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("无法打开这本书", style = MaterialTheme.typography.titleLarge)
            Text(
                text = when (code) {
                    "book.not_downloaded" -> "EPUB 尚未下载。请先在 Item 页面下载。"
                    "book.parse_failed" -> "EPUB 解析失败；请检查文件或重新下载。"
                    "book.reader_unavailable" -> "阅读器尚未初始化，请重新打开 App。"
                    else -> "文件缺失或已损坏。"
                },
                color = ReaderColors.Muted,
                modifier = Modifier.padding(top = 8.dp),
            )
        }
    }
}

@Composable
private fun ChapterRow(
    chapter: BookChapterEntity,
    selected: Boolean,
    onClick: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            "${chapter.chapterIndex + 1}",
            style = MaterialTheme.typography.labelMedium,
            color = if (selected) ReaderColors.Accent else ReaderColors.Muted,
            modifier = Modifier.size(28.dp),
        )
        Text(
            chapter.title?.takeIf { it.isNotBlank() } ?: "第 ${chapter.chapterIndex + 1} 章",
            style = MaterialTheme.typography.bodyMedium,
            color = if (selected) ReaderColors.Accent else ReaderColors.Ink,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}

@Composable
private fun SearchSheet(
    state: ReaderUiState,
    onQuery: (String) -> Unit,
    onResult: (ReaderSearchMatch) -> Unit,
) {
    Column(modifier = Modifier.padding(horizontal = 20.dp)) {
        Text("书内搜索", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = state.searchQuery,
            onValueChange = onQuery,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 10.dp)
                .testTag("reader-search-input"),
            placeholder = { Text("输入关键词") },
            singleLine = true,
            shape = RoundedCornerShape(12.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = ReaderColors.Line,
                unfocusedBorderColor = ReaderColors.Line,
                focusedContainerColor = ReaderColors.Paper,
                unfocusedContainerColor = ReaderColors.Paper,
                focusedTextColor = ReaderColors.Ink,
                unfocusedTextColor = ReaderColors.Ink,
            ),
        )
        when {
            state.searching -> Text(
                "搜索中…",
                color = ReaderColors.Muted,
                modifier = Modifier.padding(top = 12.dp),
            )

            state.searchError != null -> Text(
                state.searchError,
                color = ReaderColors.Danger,
                modifier = Modifier.padding(top = 12.dp),
            )

            state.searchQuery.isNotBlank() && state.searchResults.isEmpty() -> Text(
                "没有命中。",
                color = ReaderColors.Muted,
                modifier = Modifier.padding(top = 12.dp),
            )

            else -> LazyColumn(modifier = Modifier.heightIn(max = 340.dp)) {
                items(state.searchResults) { match ->
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onResult(match) }
                            .padding(vertical = 10.dp),
                    ) {
                        Text(
                            match.excerpt,
                            style = MaterialTheme.typography.bodySmall,
                            color = ReaderColors.Ink,
                            maxLines = 3,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ReaderSettings(
    settings: ReaderTextSettings,
    onChange: (ReaderTextSettings) -> Unit,
) {
    Column(modifier = Modifier.padding(horizontal = 20.dp)) {
        Text("阅读设置", style = MaterialTheme.typography.titleMedium)
        Text(
            "字号 ${(settings.fontSize * 100).toInt()}%",
            style = MaterialTheme.typography.labelMedium,
            color = ReaderColors.Muted,
            modifier = Modifier.padding(top = 14.dp),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ReaderSettingButton("A−") {
                onChange(settings.copy(fontSize = (settings.fontSize - 0.1).coerceAtLeast(0.7)))
            }
            ReaderSettingButton("A+") {
                onChange(settings.copy(fontSize = (settings.fontSize + 0.1).coerceAtMost(1.8)))
            }
        }
        Text(
            "行高 ${"%.1f".format(settings.lineHeight)}",
            style = MaterialTheme.typography.labelMedium,
            color = ReaderColors.Muted,
            modifier = Modifier.padding(top = 16.dp),
        )
        Slider(
            value = settings.lineHeight.toFloat(),
            onValueChange = {
                onChange(settings.copy(lineHeight = it.toDouble().coerceIn(1.1, 2.2)))
            },
            valueRange = 1.1f..2.2f,
        )
        Text(
            "主题",
            style = MaterialTheme.typography.labelMedium,
            color = ReaderColors.Muted,
            modifier = Modifier.padding(top = 8.dp),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ReaderThemeChoice.entries.forEach { choice ->
                ReaderSettingButton(
                    choice.label,
                    selected = settings.theme == choice,
                ) {
                    onChange(settings.copy(theme = choice))
                }
            }
        }
    }
}

@Composable
private fun ReaderSettingButton(
    label: String,
    selected: Boolean = false,
    onClick: () -> Unit,
) {
    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = if (selected) ReaderColors.Ink else Color.Transparent,
        contentColor = if (selected) ReaderColors.Paper else ReaderColors.Muted,
        border = androidx.compose.foundation.BorderStroke(1.dp, ReaderColors.Line),
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 7.dp),
        )
    }
}
