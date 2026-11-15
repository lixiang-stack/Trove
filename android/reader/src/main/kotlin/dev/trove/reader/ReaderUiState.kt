package dev.trove.reader

import dev.trove.core.db.BookChapterEntity
import org.readium.r2.navigator.epub.EpubPreferences
import org.readium.r2.navigator.preferences.Theme
import org.readium.r2.shared.ExperimentalReadiumApi
import org.readium.r2.shared.publication.Locator

enum class ReaderThemeChoice(val label: String) {
    LIGHT("浅色"),
    SEPIA("护眼"),
    DARK("深色"),
}

data class ReaderTextSettings(
    val fontSize: Double = 1.0,
    val lineHeight: Double = 1.5,
    val theme: ReaderThemeChoice = ReaderThemeChoice.LIGHT,
) {
    @OptIn(ExperimentalReadiumApi::class)
    fun toPreferences(): EpubPreferences = EpubPreferences(
        fontSize = fontSize,
        lineHeight = lineHeight,
        theme = when (theme) {
            ReaderThemeChoice.LIGHT -> Theme.LIGHT
            ReaderThemeChoice.SEPIA -> Theme.SEPIA
            ReaderThemeChoice.DARK -> Theme.DARK
        },
    )
}

data class ReaderSearchMatch(
    val locator: Locator,
    val excerpt: String,
)

data class ReaderUiState(
    val loading: Boolean = true,
    val errorCode: String? = null,
    val title: String = "",
    val author: String? = null,
    val chapters: List<BookChapterEntity> = emptyList(),
    val currentChapter: Int = 0,
    val progress: Double = 0.0,
    val textSettings: ReaderTextSettings = ReaderTextSettings(),
    val finished: Boolean = false,
    val searchOpen: Boolean = false,
    val searchQuery: String = "",
    val searching: Boolean = false,
    val searchResults: List<ReaderSearchMatch> = emptyList(),
    val searchError: String? = null,
)
