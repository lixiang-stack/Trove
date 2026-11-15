package dev.trove.app.add

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import dev.trove.app.ui.components.RootTab
import dev.trove.app.ui.components.TroveBottomNav
import dev.trove.app.ui.theme.TroveColors

@Composable
fun AddScreen(
    onBack: () -> Unit,
    onLibrary: () -> Unit,
    onSearch: () -> Unit,
) {
    var url by remember { mutableStateOf("") }
    var feed by remember { mutableStateOf("") }
    var message by remember { mutableStateOf<String?>(null) }
    Scaffold(
        modifier = Modifier.testTag("add-screen"),
        containerColor = TroveColors.Paper,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            TroveBottomNav(
                selected = RootTab.ADD,
                onSelect = {
                    when (it) {
                        RootTab.LIBRARY -> onLibrary()
                        RootTab.SEARCH -> onSearch()
                        RootTab.ADD -> Unit
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
                    "添加",
                    style = MaterialTheme.typography.titleLarge,
                    color = TroveColors.Ink,
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 18.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                FieldLabel("链接")
                OutlinedTextField(
                    value = url,
                    onValueChange = { url = it },
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("B 站 / YouTube 单条视频 URL") },
                    singleLine = true,
                    shape = RoundedCornerShape(12.dp),
                    colors = fieldColors(),
                )
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = TroveColors.Paper2,
                    border = androidx.compose.foundation.BorderStroke(
                        1.dp,
                        TroveColors.Line,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Text(
                            "选择本地音频 / 视频 / EPUB",
                            style = MaterialTheme.typography.labelMedium,
                            color = TroveColors.Ink,
                        )
                        Text(
                            "请在 Host Console 上传",
                            style = MaterialTheme.typography.labelSmall,
                            color = TroveColors.Muted,
                        )
                    }
                }
                FieldLabel("播客 feed")
                OutlinedTextField(
                    value = feed,
                    onValueChange = { feed = it },
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("粘贴 RSS feed URL，预览最近单集") },
                    singleLine = true,
                    shape = RoundedCornerShape(12.dp),
                    colors = fieldColors(),
                )
                Text(
                    "转写/书文本会分块发送给 DeepSeek 生成摘要和 Tag。Android Add 将在下一阶段接入 Host；当前可使用 Host Console 添加内容。",
                    style = MaterialTheme.typography.bodySmall,
                    color = TroveColors.Muted,
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(TroveColors.Paper2, RoundedCornerShape(10.dp))
                        .padding(10.dp),
                )
                if (message != null) {
                    Text(
                        message.orEmpty(),
                        style = MaterialTheme.typography.bodySmall,
                        color = TroveColors.Accent,
                    )
                }
                Surface(
                    onClick = {
                        message = "Android Add 尚未接入 Host。请先在 Host Console 添加，Library 会自动同步。"
                    },
                    shape = CircleShape,
                    color = TroveColors.Accent,
                    contentColor = TroveColors.White,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    androidx.compose.foundation.layout.Box(
                        modifier = Modifier.fillMaxWidth(),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text(
                            "开始处理",
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(vertical = 13.dp),
                        )
                    }
                }
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}

@Composable
private fun FieldLabel(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.labelMedium,
        color = TroveColors.Muted,
    )
}

@Composable
private fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = TroveColors.Line,
    unfocusedBorderColor = TroveColors.Line,
    focusedContainerColor = TroveColors.Paper2,
    unfocusedContainerColor = TroveColors.Paper2,
    focusedTextColor = TroveColors.Ink,
    unfocusedTextColor = TroveColors.Ink,
    cursorColor = TroveColors.Accent,
)
