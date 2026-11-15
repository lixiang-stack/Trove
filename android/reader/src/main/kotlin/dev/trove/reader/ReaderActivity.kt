package dev.trove.reader

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.webkit.WebSettings
import android.webkit.WebView
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import androidx.core.view.WindowCompat
import dev.trove.core.db.BookChapterEntity
import dev.trove.core.library.LibraryItem
import dev.trove.core.reading.BookLoadResult
import dev.trove.core.reading.BookLocator
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.readium.r2.navigator.Decoration
import org.readium.r2.navigator.epub.EpubNavigatorFactory
import org.readium.r2.navigator.epub.EpubNavigatorFragment
import org.readium.r2.shared.publication.Locator
import org.readium.r2.shared.publication.Publication
import org.readium.r2.shared.publication.services.search.SearchService
import org.readium.r2.shared.publication.services.search.StringSearchService
import org.readium.r2.shared.publication.services.search.search
import org.readium.r2.shared.ExperimentalReadiumApi
import org.readium.r2.shared.util.AbsoluteUrl
import org.readium.r2.shared.util.Url
import org.readium.r2.shared.util.asset.AssetRetriever
import org.readium.r2.shared.util.http.DefaultHttpClient
import org.readium.r2.shared.util.mediatype.MediaType
import org.readium.r2.streamer.PublicationOpener
import org.readium.r2.streamer.parser.DefaultPublicationParser
import java.io.File

data class ReaderArgs(
    val itemId: String,
    val chapterIndex: Int? = null,
    val paragraphIndex: Int? = null,
    val epubHref: String? = null,
    val epubProgression: Double? = null,
) {
    fun toIntent(context: Context): Intent = Intent(context, ReaderActivity::class.java).apply {
        putExtra(EXTRA_ITEM_ID, itemId)
        chapterIndex?.let { putExtra(EXTRA_CHAPTER, it) }
        paragraphIndex?.let { putExtra(EXTRA_PARAGRAPH, it) }
        epubHref?.let { putExtra(EXTRA_HREF, it) }
        epubProgression?.let { putExtra(EXTRA_PROGRESSION, it) }
    }

    companion object {
        const val EXTRA_ITEM_ID = "dev.trove.reader.ITEM_ID"
        const val EXTRA_CHAPTER = "dev.trove.reader.CHAPTER"
        const val EXTRA_PARAGRAPH = "dev.trove.reader.PARAGRAPH"
        const val EXTRA_HREF = "dev.trove.reader.HREF"
        const val EXTRA_PROGRESSION = "dev.trove.reader.PROGRESSION"

        fun from(intent: Intent): ReaderArgs? {
            val itemId = intent.getStringExtra(EXTRA_ITEM_ID) ?: return null
            return ReaderArgs(
                itemId = itemId,
                chapterIndex = intent.getIntExtra(EXTRA_CHAPTER, -1).takeIf { it >= 0 },
                paragraphIndex = intent.getIntExtra(EXTRA_PARAGRAPH, -1).takeIf { it >= 0 },
                epubHref = intent.getStringExtra(EXTRA_HREF),
                epubProgression = intent.getDoubleExtra(EXTRA_PROGRESSION, -1.0)
                    .takeIf { it >= 0.0 },
            )
        }
    }
}

@OptIn(ExperimentalReadiumApi::class)
private const val SEARCH_HIGHLIGHT_TINT = 0x55B5462F

class ReaderActivity : FragmentActivity() {
    private val args: ReaderArgs? by lazy { ReaderArgs.from(intent) }
    private var publication: Publication? = null
    private var navigator: EpubNavigatorFragment? = null
    private var initialLocator: Locator? = null
    private var highlightLocator: Locator? = null
    private var currentLocator: Locator? = null
    private var saveJob: Job? = null
    private var paragraphCounts: Map<Int, Int> = emptyMap()
    private var uiState by mutableStateOf(ReaderUiState())
    private var attached = false

    private val readerDependencies: ReaderDependencies?
        get() = (application as? ReaderHost)?.readerDependencies

    @OptIn(ExperimentalReadiumApi::class)
    private val listener = object : EpubNavigatorFragment.Listener {
        override fun onExternalLinkActivated(url: AbsoluteUrl) {
            // External navigation is deliberately blocked: EPUB content is untrusted.
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        WindowCompat.getInsetsController(window, window.decorView).isAppearanceLightStatusBars = true
        setContent {
            ReaderTheme {
                ReaderScreen(
                    state = uiState,
                    onBack = { finish() },
                    onChapter = ::openChapter,
                    onSearchOpen = { update { it.copy(searchOpen = true) } },
                    onSearchClose = { update { it.copy(searchOpen = false) } },
                    onSearchQuery = ::search,
                    onSearchResult = ::openSearchResult,
                    onSettings = ::applySettings,
                    onToggleFinished = ::toggleFinished,
                    onReaderContainer = ::attachNavigator,
                )
            }
        }
        if (args == null) {
            update { it.copy(loading = false, errorCode = "book.missing") }
        } else {
            load()
        }
    }

    private fun load() {
        val request = args ?: return
        val dependencies = readerDependencies
        if (dependencies == null) {
            update { it.copy(loading = false, errorCode = "book.reader_unavailable") }
            return
        }
        lifecycleScope.launch {
            val loaded = withContext(Dispatchers.IO) {
                runCatching {
                    val item = dependencies.libraryRepository.find(request.itemId)
                        ?: error("book.missing")
                    val file = dependencies.bookRepository.epubFile(request.itemId)
                        ?: error("book.not_downloaded")
                    when (dependencies.bookRepository.ensureParsed(request.itemId)) {
                        is BookLoadResult.Ready -> Unit
                        BookLoadResult.NotDownloaded -> error("book.not_downloaded")
                        BookLoadResult.Failed -> error("book.parse_failed")
                    }
                    val chapters = dependencies.bookRepository.chapters(request.itemId)
                    val paragraphs = dependencies.database.bookDao()
                        .paragraphs(request.itemId)
                    val counts = paragraphs.groupingBy { it.chapterIndex }.eachCount()
                    val publication = openPublication(file)
                    val stored = BookLocator.parse(item.bookLocator)
                    var locator = locatorFor(request, stored, publication)
                    var highlight: Locator? = null
                    if (request.chapterIndex != null &&
                        request.paragraphIndex != null &&
                        request.epubHref == null
                    ) {
                        val paragraph = paragraphs.firstOrNull {
                            it.chapterIndex == request.chapterIndex &&
                                it.paragraphIndex == request.paragraphIndex
                        }?.text
                        if (!paragraph.isNullOrBlank()) {
                            highlight = findLocator(publication, paragraph)
                            if (highlight != null) locator = highlight
                        }
                    }
                    LoadedReader(
                        item = item,
                        chapters = chapters,
                        paragraphCounts = counts,
                        publication = publication,
                        storedLocator = stored,
                        initialLocator = locator,
                        highlightLocator = highlight,
                    )
                }
            }
            loaded.onSuccess { result ->
                publication = result.publication
                paragraphCounts = result.paragraphCounts
                initialLocator = result.initialLocator
                highlightLocator = result.highlightLocator
                val stored = result.storedLocator
                update {
                    it.copy(
                        loading = false,
                        title = result.item.title,
                        author = result.item.author,
                        chapters = result.chapters,
                        currentChapter = ReaderLocatorMapping.initialChapter(
                            stored,
                            result.publication.readingOrder.size,
                        ),
                        progress = stored?.fraction ?: 0.0,
                        finished = result.item.consumptionState == "finished",
                    )
                }
                window.decorView.post { attachNavigator() }
            }.onFailure { error ->
                update { it.copy(loading = false, errorCode = error.message ?: "book.parse_failed") }
            }
        }
    }

    @OptIn(ExperimentalReadiumApi::class)
    private suspend fun findLocator(publication: Publication, text: String): Locator? {
        val iterator = publication.search(text.take(80)) ?: return null
        return try {
            iterator.next().getOrNull()?.locators?.firstOrNull()
        } finally {
            iterator.close()
        }
    }

    @OptIn(ExperimentalReadiumApi::class)
    private suspend fun openPublication(file: File): Publication = withContext(Dispatchers.IO) {
        val retriever = AssetRetriever(contentResolver, DefaultHttpClient())
        val asset = retriever.retrieve(file, MediaType.EPUB).getOrNull()
            ?: throw IllegalStateException("book.parse_failed")
        val opener = PublicationOpener(
            DefaultPublicationParser(applicationContext, DefaultHttpClient(), retriever, null)
        )
        opener.open(
            asset,
            allowUserInteraction = false,
            onCreatePublication = {
                servicesBuilder.set(
                    SearchService::class,
                    StringSearchService.createDefaultFactory(),
                )
            },
        ).getOrNull() ?: throw IllegalStateException("book.parse_failed")
    }

    private fun locatorFor(
        request: ReaderArgs,
        stored: BookLocator?,
        publication: Publication,
    ): Locator {
        val readingOrder = publication.readingOrder
        val chapterIndex = request.chapterIndex
            ?: ReaderLocatorMapping.initialChapter(stored, readingOrder.size)
        request.epubHref?.let { href ->
            return epubLocator(href, request.epubProgression, request.epubProgression)
        }
        if (request.chapterIndex != null) {
            val link = readingOrder.getOrNull(chapterIndex)
            if (link != null) {
                val locator = publication.locatorFromLink(link)
                    ?: return epubLocator(readingOrder.firstOrNull()?.href?.toString().orEmpty(), 0.0, 0.0)
                return locator
            }
        }
        stored?.epubHref?.let { href ->
            return epubLocator(href, stored.epubProgression, stored.epubTotalProgression)
        }
        val link = readingOrder.getOrNull(chapterIndex)
        if (link != null) {
            val locator = publication.locatorFromLink(link)
                ?: return epubLocator(readingOrder.firstOrNull()?.href?.toString().orEmpty(), 0.0, 0.0)
            val fraction = stored?.fraction ?: request.epubProgression ?: 0.0
            return locator.copyWithLocations(
                progression = fraction,
                totalProgression = fraction,
            )
        }
        return epubLocator(readingOrder.firstOrNull()?.href?.toString().orEmpty(), 0.0, 0.0)
    }

    private fun epubLocator(
        href: String,
        progression: Double?,
        totalProgression: Double?,
    ): Locator {
        val url = requireNotNull(Url(href)) { "Invalid EPUB href: $href" }
        val mediaType = MediaType("application/xhtml+xml") ?: MediaType.BINARY
        return Locator(
            href = url,
            mediaType = mediaType,
            title = null,
            locations = Locator.Locations(
                progression = progression,
                totalProgression = totalProgression,
            ),
            text = Locator.Text(),
        )
    }

    private fun attachNavigator() {
        if (attached) return
        val pub = publication ?: return
        val container = findViewById<View>(R.id.reader_container) ?: return
        attached = true
        val factory = EpubNavigatorFactory(pub, EpubNavigatorFactory.Configuration())
            .createFragmentFactory(
                initialLocator = initialLocator,
                initialPreferences = uiState.textSettings.toPreferences(),
                listener = listener,
            )
        supportFragmentManager.fragmentFactory = factory
        supportFragmentManager.beginTransaction()
            .replace(container.id, EpubNavigatorFragment::class.java, null)
            .commitNowAllowingStateLoss()
        val fragment = supportFragmentManager.findFragmentById(container.id)
            as? EpubNavigatorFragment ?: return
        navigator = fragment
        highlightLocator?.let { locator ->
            lifecycleScope.launch {
                runCatching {
                    fragment.applyDecorations(
                        listOf(
                            Decoration(
                                id = "search-hit",
                                locator = locator,
                                style = Decoration.Style.Highlight(tint = SEARCH_HIGHLIGHT_TINT),
                            )
                        ),
                        group = "search",
                    )
                }
            }
        }
        hardenWebViews(fragment.requireView())
        lifecycleScope.launch {
            fragment.currentLocator.collect { locator ->
                onLocatorChanged(locator)
            }
        }
    }

    private fun onLocatorChanged(locator: Locator) {
        currentLocator = locator
        val readingOrder = publication?.readingOrder?.map { it.href.toString() } ?: emptyList()
        val chapter = ReaderLocatorMapping.chapterIndexForHref(
            locator.href.toString(),
            readingOrder,
        )
        update {
            it.copy(
                currentChapter = chapter,
                progress = (locator.locations.totalProgression
                    ?: locator.locations.progression
                    ?: it.progress).coerceIn(0.0, 1.0),
            )
        }
        hardenWebViews(navigator?.view)
        saveJob?.cancel()
        saveJob = lifecycleScope.launch {
            delay(1_200)
            persist(locator)
        }
    }

    private suspend fun persist(locator: Locator, readingOrder: List<String>? = null) {
        val request = args ?: return
        val dependencies = readerDependencies ?: return
        val order = readingOrder
            ?: publication?.readingOrder?.map { it.href.toString() }
            ?: return
        val chapter = ReaderLocatorMapping.chapterIndexForHref(
            locator.href.toString(),
            order,
        )
        val progression = locator.locations.progression
        val total = locator.locations.totalProgression
        val paragraphs = paragraphCounts[chapter] ?: 0
        val paragraph = if (paragraphs > 0 && progression != null) {
            (progression * paragraphs).toInt().coerceIn(0, paragraphs - 1)
        } else {
            null
        }
        val bookLocator = ReaderLocatorMapping.toBookLocator(
            chapterIndex = chapter,
            paragraphIndex = paragraph,
            href = locator.href.toString(),
            progression = progression,
            totalProgression = total,
        )
        runCatching { dependencies.itemMutationRepository.saveBookProgress(request.itemId, bookLocator) }
    }

    private fun openChapter(index: Int) {
        val pub = publication ?: return
        val link = pub.readingOrder.getOrNull(index) ?: return
        pub.locatorFromLink(link)?.let { navigator?.go(it) }
    }

    @OptIn(ExperimentalReadiumApi::class)
    private fun search(query: String) {
        update { it.copy(searchQuery = query, searchError = null) }
        if (query.isBlank()) {
            update { it.copy(searching = false, searchResults = emptyList()) }
            return
        }
        val pub = publication ?: return
        update { it.copy(searching = true) }
        lifecycleScope.launch {
            val results = withContext(Dispatchers.IO) {
                runCatching {
                    val iterator = pub.search(query)
                        ?: return@runCatching emptyList<ReaderSearchMatch>()
                    val matches = mutableListOf<ReaderSearchMatch>()
                    try {
                        while (matches.size < 50) {
                            val page = iterator.next().getOrNull() ?: break
                            if (page.locators.isEmpty()) break
                            for (locator in page.locators) {
                                matches += ReaderSearchMatch(
                                    locator = locator,
                                    excerpt = listOfNotNull(
                                        locator.text.before?.takeLast(40),
                                        locator.text.highlight,
                                        locator.text.after?.take(40),
                                    ).joinToString(""),
                                )
                            }
                        }
                    } finally {
                        iterator.close()
                    }
                    matches
                }
            }
            results.onSuccess {
                update { state -> state.copy(searching = false, searchResults = it) }
            }.onFailure {
                update { state ->
                    state.copy(searching = false, searchError = "搜索失败，请重试。")
                }
            }
        }
    }

    private fun openSearchResult(match: ReaderSearchMatch) {
        navigator?.go(match.locator)
        lifecycleScope.launch {
            runCatching {
                navigator?.applyDecorations(
                    listOf(
                        Decoration(
                            id = "search-hit",
                            locator = match.locator,
                            style = Decoration.Style.Highlight(tint = SEARCH_HIGHLIGHT_TINT),
                        )
                    ),
                    group = "search",
                )
            }
        }
        update { it.copy(searchOpen = false) }
    }

    private fun applySettings(settings: ReaderTextSettings) {
        update { it.copy(textSettings = settings) }
        navigator?.submitPreferences(settings.toPreferences())
    }

    private fun toggleFinished() {
        val request = args ?: return
        val dependencies = readerDependencies ?: return
        val next = !uiState.finished
        update { it.copy(finished = next) }
        lifecycleScope.launch {
            runCatching {
                dependencies.itemMutationRepository.setConsumption(
                    request.itemId,
                    if (next) "finished" else "unstarted",
                )
            }
        }
    }

    private fun update(block: (ReaderUiState) -> ReaderUiState) {
        uiState = block(uiState)
    }

    private fun hardenWebViews(view: View?) {
        if (view == null) return
        if (view is WebView) {
            runCatching { view.settings.blockNetworkLoads = true }
            runCatching {
                view.settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            }
            runCatching {
                view.settings.javaScriptCanOpenWindowsAutomatically = false
            }
            runCatching { view.settings.setSupportMultipleWindows(false) }
            return
        }
        if (view is ViewGroup) {
            for (index in 0 until view.childCount) {
                hardenWebViews(view.getChildAt(index))
            }
        }
    }

    override fun onPause() {
        saveJob?.cancel()
        val locator = currentLocator
        if (locator != null) {
            val order = publication?.readingOrder?.map { it.href.toString() }.orEmpty()
            lifecycleScope.launch(NonCancellable + Dispatchers.IO) { persist(locator, order) }
        }
        super.onPause()
    }

    override fun onDestroy() {
        publication?.close()
        publication = null
        super.onDestroy()
    }

    private data class LoadedReader(
        val item: LibraryItem,
        val chapters: List<BookChapterEntity>,
        val paragraphCounts: Map<Int, Int>,
        val publication: Publication,
        val storedLocator: BookLocator?,
        val initialLocator: Locator,
        val highlightLocator: Locator?,
    )
}
