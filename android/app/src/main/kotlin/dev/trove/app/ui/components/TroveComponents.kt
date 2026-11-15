package dev.trove.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil3.compose.AsyncImage
import dev.trove.app.ui.theme.TroveColors
import dev.trove.core.library.LibraryItem
import java.io.File

data class CoverPaint(val start: Color, val end: Color)

fun coverPaint(item: LibraryItem): CoverPaint {
    val key = when {
        item.platform == "youtube" -> 2
        item.platform == "podcast" -> 1
        item.sourceType == "epub" -> 4
        item.sourceType == "podcast_episode" -> 1
        else -> ((item.id.hashCode() * 31 + item.title.hashCode()) and 0x7fffffff) % 6
    }
    val palette = listOf(
        CoverPaint(Color(0xFFB5462F), Color(0xFF762B20)),
        CoverPaint(Color(0xFF356657), Color(0xFF1D3D34)),
        CoverPaint(Color(0xFF3C5A78), Color(0xFF22364A)),
        CoverPaint(Color(0xFFB58A2F), Color(0xFF765719)),
        CoverPaint(Color(0xFF3A3731), Color(0xFF1B1917)),
        CoverPaint(Color(0xFFA8684A), Color(0xFF693B2A)),
    )
    return palette[key % palette.size]
}

@Composable
fun TroveCover(
    item: LibraryItem,
    size: Dp,
    modifier: Modifier = Modifier,
    corner: Dp = size * 0.19f,
) {
    val localCover = item.coverArtifact?.localPath?.let(::File)?.takeIf { it.isFile }
    val shape = RoundedCornerShape(corner)
    if (localCover != null) {
        AsyncImage(
            model = localCover,
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = modifier
                .size(size)
                .clip(shape),
        )
        return
    }
    val paint = coverPaint(item)
    val initial = item.title.firstOrNull()?.toString() ?: "拾"
    Box(
        modifier = modifier
            .size(size)
            .clip(shape)
            .background(Brush.linearGradient(listOf(paint.start, paint.end)))
            .drawBehind {
                val step = this.size.minDimension / 5f
                val stroke = Color.White.copy(alpha = 0.04f)
                var x = -this.size.height
                while (x < this.size.width) {
                    drawLine(
                        color = stroke,
                        start = Offset(x, 0f),
                        end = Offset(x + this.size.height, this.size.height),
                        strokeWidth = 1.dp.toPx(),
                    )
                    x += step
                }
            },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text = initial,
            color = TroveColors.White,
            fontFamily = FontFamily.Serif,
            fontWeight = FontWeight.SemiBold,
            fontSize = (size.value * 0.42f).sp,
        )
    }
}

@Composable
fun TroveChip(
    label: String,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    testTag: String? = null,
) {
    val background = if (selected) TroveColors.Ink else Color.Transparent
    val content = if (selected) TroveColors.Paper else TroveColors.Muted
    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = background,
        contentColor = content,
        border = BorderStroke(1.dp, if (selected) TroveColors.Ink else TroveColors.Line),
        modifier = modifier.then(
            if (testTag != null) Modifier.testTag(testTag) else Modifier
        ),
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = 11.dp, vertical = 6.dp),
        )
    }
}

@Composable
fun TroveRoundButton(
    icon: ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    size: Dp = 38.dp,
    iconSize: Dp = 19.dp,
    background: Color = Color.Transparent,
    contentColor: Color = TroveColors.Ink,
    border: Color? = null,
    testTag: String? = null,
) {
    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = background,
        contentColor = contentColor,
        border = border?.let { BorderStroke(1.dp, it) },
        modifier = modifier.then(
            if (testTag != null) Modifier.testTag(testTag) else Modifier
        ),
    ) {
        Box(Modifier.size(size), contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = contentDescription, modifier = Modifier.size(iconSize))
        }
    }
}

@Composable
fun TinyProgress(
    fraction: Float,
    modifier: Modifier = Modifier,
    track: Color = TroveColors.Line,
    fill: Color = TroveColors.Accent,
    height: Dp = 2.dp,
) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(height)
            .clip(CircleShape)
            .background(track),
    ) {
        Box(
            Modifier
                .fillMaxWidth(fraction.coerceIn(0f, 1f))
                .height(height)
                .clip(CircleShape)
                .background(fill),
        )
    }
}

@Composable
fun TrovePill(
    text: String,
    onClick: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
    dark: Boolean = false,
) {
    val border = if (dark) Color.White.copy(alpha = 0.14f) else TroveColors.Line
    val color = if (dark) TroveColors.Paper.copy(alpha = 0.68f) else TroveColors.Muted
    Surface(
        shape = CircleShape,
        color = Color.Transparent,
        border = BorderStroke(1.dp, border),
        modifier = modifier.then(
            if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier
        ),
    ) {
        Text(
            text = text,
            color = color,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp),
        )
    }
}

@Composable
fun TroveEmpty(
    title: String,
    copy: String,
    action: String? = null,
    onAction: (() -> Unit)? = null,
    dark: Boolean = false,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 24.dp, vertical = 52.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier
                .size(62.dp)
                .clip(CircleShape)
                .background(if (dark) TroveColors.Paper else TroveColors.Ink),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                "拾",
                color = if (dark) TroveColors.Ink else TroveColors.Paper,
                fontFamily = FontFamily.Serif,
                fontSize = 26.sp,
            )
        }
        Text(
            title,
            style = MaterialTheme.typography.titleLarge,
            color = if (dark) TroveColors.Paper else TroveColors.Ink,
            modifier = Modifier.padding(top = 14.dp),
            textAlign = TextAlign.Center,
        )
        Text(
            copy,
            style = MaterialTheme.typography.bodyMedium,
            color = if (dark) TroveColors.Paper.copy(alpha = 0.52f) else TroveColors.Muted,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 6.dp),
        )
        if (action != null && onAction != null) {
            Surface(
                onClick = onAction,
                shape = CircleShape,
                color = TroveColors.Accent,
                contentColor = TroveColors.White,
                modifier = Modifier.padding(top = 16.dp),
            ) {
                Text(
                    action,
                    style = MaterialTheme.typography.labelLarge,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 11.dp),
                )
            }
        }
    }
}

enum class RootTab(val label: String, val icon: ImageVector) {
    LIBRARY("资料库", Icons.AutoMirrored.Filled.List),
    SEARCH("搜索", Icons.Filled.Search),
    ADD("添加", Icons.Filled.Add),
}

@Composable
fun TroveBottomNav(
    selected: RootTab,
    onSelect: (RootTab) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(TroveColors.Paper2)
            .padding(horizontal = 8.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        RootTab.entries.forEach { tab ->
            val active = tab == selected
            Surface(
                onClick = { onSelect(tab) },
                shape = RoundedCornerShape(12.dp),
                color = if (active) TroveColors.Ink.copy(alpha = 0.06f) else Color.Transparent,
                contentColor = if (active) TroveColors.Ink else TroveColors.Muted,
                modifier = Modifier.weight(1f),
            ) {
                Column(
                    modifier = Modifier.padding(vertical = 6.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(3.dp),
                ) {
                    Icon(tab.icon, contentDescription = null, modifier = Modifier.size(19.dp))
                    Text(tab.label, style = MaterialTheme.typography.labelSmall)
                }
            }
        }
    }
}

@Composable
fun TroveIconButton(
    icon: ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    tint: Color = TroveColors.Ink,
    testTag: String? = null,
) {
    IconButton(
        onClick = onClick,
        colors = IconButtonDefaults.iconButtonColors(contentColor = tint),
        modifier = modifier.then(
            if (testTag != null) Modifier.testTag(testTag) else Modifier
        ),
    ) {
        Icon(icon, contentDescription, modifier = Modifier.size(21.dp))
    }
}
