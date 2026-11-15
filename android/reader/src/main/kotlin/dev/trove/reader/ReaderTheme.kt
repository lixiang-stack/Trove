package dev.trove.reader

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * Reader is its own Gradle module and cannot depend on :app, so these tokens
 * intentionally mirror app/ui/theme/Theme.kt. Keep them in sync when the
 * palette changes.
 */
object ReaderColors {
    val Paper = Color(0xFFF4EFE6)
    val Paper2 = Color(0xFFFBF8F2)
    val Ink = Color(0xFF1F1D1A)
    val Muted = Color(0xFF746E64)
    val Line = Color(0xFFDDD5C8)
    val Accent = Color(0xFFB5462F)
    val White = Color(0xFFFFFDF8)
    val Danger = Color(0xFFA54535)
}

private val ReaderTypography = Typography(
    titleLarge = TextStyle(
        fontFamily = FontFamily.Serif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = FontFamily.Serif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 17.sp,
    ),
    bodyMedium = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 13.sp),
    bodySmall = TextStyle(fontFamily = FontFamily.SansSerif, fontSize = 11.sp),
    labelMedium = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = FontFamily.SansSerif,
        fontWeight = FontWeight.Medium,
        fontSize = 10.sp,
    ),
)

private val ReaderScheme = lightColorScheme(
    primary = ReaderColors.Accent,
    onPrimary = ReaderColors.White,
    background = ReaderColors.Paper,
    onBackground = ReaderColors.Ink,
    surface = ReaderColors.Paper2,
    onSurface = ReaderColors.Ink,
    surfaceVariant = ReaderColors.Paper,
    onSurfaceVariant = ReaderColors.Muted,
    outline = ReaderColors.Line,
    error = ReaderColors.Danger,
)

@Composable
fun ReaderTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = ReaderScheme, typography = ReaderTypography, content = content)
}
