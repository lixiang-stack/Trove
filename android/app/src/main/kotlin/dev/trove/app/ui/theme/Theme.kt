package dev.trove.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

object TroveColors {
    val Paper = Color(0xFFF4EFE6)
    val Paper2 = Color(0xFFFBF8F2)
    val Ink = Color(0xFF1F1D1A)
    val Muted = Color(0xFF746E64)
    val Line = Color(0xFFDDD5C8)
    val Accent = Color(0xFFB5462F)
    val AccentSoft = Color(0xFFE8C9BF)
    val Green = Color(0xFF2F5D50)
    val Gold = Color(0xFFB58A2F)
    val Player = Color(0xFF171614)
    val PlayerPanel = Color(0xFF1D1B18)
    val White = Color(0xFFFFFDF8)
    val Danger = Color(0xFFA54535)
    val Cooking = Color(0xFF8C6A23)
}

private val Serif = FontFamily.Serif
private val Sans = FontFamily.SansSerif

private val TroveTypography = Typography(
    displaySmall = TextStyle(
        fontFamily = Serif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 32.sp,
        lineHeight = 38.sp,
    ),
    headlineMedium = TextStyle(
        fontFamily = Serif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 27.sp,
        lineHeight = 33.sp,
    ),
    titleLarge = TextStyle(
        fontFamily = Serif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
        lineHeight = 26.sp,
    ),
    titleMedium = TextStyle(
        fontFamily = Serif,
        fontWeight = FontWeight.SemiBold,
        fontSize = 17.sp,
        lineHeight = 23.sp,
    ),
    titleSmall = TextStyle(
        fontFamily = Sans,
        fontWeight = FontWeight.SemiBold,
        fontSize = 13.sp,
        lineHeight = 18.sp,
    ),
    bodyLarge = TextStyle(
        fontFamily = Sans,
        fontSize = 15.sp,
        lineHeight = 24.sp,
    ),
    bodyMedium = TextStyle(
        fontFamily = Sans,
        fontSize = 13.sp,
        lineHeight = 20.sp,
    ),
    bodySmall = TextStyle(
        fontFamily = Sans,
        fontSize = 11.sp,
        lineHeight = 16.sp,
    ),
    labelLarge = TextStyle(
        fontFamily = Sans,
        fontWeight = FontWeight.SemiBold,
        fontSize = 12.sp,
        lineHeight = 16.sp,
    ),
    labelMedium = TextStyle(
        fontFamily = Sans,
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        lineHeight = 15.sp,
    ),
    labelSmall = TextStyle(
        fontFamily = Sans,
        fontWeight = FontWeight.Medium,
        fontSize = 10.sp,
        lineHeight = 14.sp,
        letterSpacing = 0.2.sp,
    ),
)

private val TroveShapes = Shapes(
    extraSmall = androidx.compose.foundation.shape.RoundedCornerShape(6.dp),
    small = androidx.compose.foundation.shape.RoundedCornerShape(10.dp),
    medium = androidx.compose.foundation.shape.RoundedCornerShape(14.dp),
    large = androidx.compose.foundation.shape.RoundedCornerShape(18.dp),
    extraLarge = androidx.compose.foundation.shape.RoundedCornerShape(22.dp),
)

private val TroveColorsScheme = lightColorScheme(
    primary = TroveColors.Accent,
    onPrimary = TroveColors.White,
    primaryContainer = TroveColors.AccentSoft,
    onPrimaryContainer = TroveColors.Accent,
    secondary = TroveColors.Green,
    onSecondary = TroveColors.White,
    background = TroveColors.Paper,
    onBackground = TroveColors.Ink,
    surface = TroveColors.Paper2,
    onSurface = TroveColors.Ink,
    surfaceVariant = TroveColors.Paper,
    onSurfaceVariant = TroveColors.Muted,
    outline = TroveColors.Line,
    outlineVariant = TroveColors.Line,
    error = TroveColors.Danger,
    onError = TroveColors.White,
)

@Composable
fun TroveTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = TroveColorsScheme,
        typography = TroveTypography,
        shapes = TroveShapes,
        content = content,
    )
}
