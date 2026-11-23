package dev.trove.app

import androidx.compose.animation.core.tween
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation3.runtime.NavKey
import androidx.navigation3.runtime.entryProvider
import androidx.navigation3.runtime.rememberNavBackStack
import androidx.navigation3.ui.NavDisplay
import dev.trove.app.add.AddScreen
import dev.trove.app.add.AddViewModel
import dev.trove.app.collection.CollectionScreen
import dev.trove.app.download.DownloadsScreen
import dev.trove.app.library.LibraryScreen
import dev.trove.app.library.LibraryViewModel
import dev.trove.app.player.PlayerScreen
import dev.trove.app.player.PlayerViewModel
import dev.trove.app.search.SearchScreen
import dev.trove.app.search.SearchViewModel
import dev.trove.app.session.LoginScreen
import dev.trove.app.session.SessionState
import dev.trove.app.session.SessionViewModel
import dev.trove.app.settings.SettingsScreen
import dev.trove.app.settings.SettingsViewModel
import dev.trove.app.transcript.TranscriptScreen
import dev.trove.app.transcript.TranscriptViewModel
import dev.trove.app.ui.components.DrawerTab
import dev.trove.app.ui.components.TroveDrawer
import dev.trove.app.ui.theme.TroveColors
import dev.trove.app.ui.theme.TroveTheme
import dev.trove.core.network.DeviceDto
import dev.trove.reader.ReaderArgs
import kotlinx.serialization.Serializable

private const val NAV_ANIMATION_MILLIS = 300
private const val NAV_PARALLAX_DIVISOR = 3

@Serializable
data object LibraryRoute : NavKey

@Serializable
data object SearchRoute : NavKey

@Serializable
data object AddRoute : NavKey

@Serializable
data class PlayerRoute(val itemId: String) : NavKey

@Serializable
data class CollectionRoute(val collectionId: String) : NavKey

@Serializable
data class TranscriptRoute(
    val itemId: String,
    val focusSeq: Int? = null,
    val query: String = "",
) : NavKey

@Serializable
data object DownloadsRoute : NavKey

@Serializable
data object SettingsRoute : NavKey

@Composable
fun TroveApp(viewModel: SessionViewModel, container: AppContainer) {
    TroveTheme {
        val state by viewModel.session.collectAsStateWithLifecycle()
        Column(modifier = Modifier.fillMaxSize()) {
            if (BuildConfig.ALLOW_LAN_CLEARTEXT) {
                LanWarningBanner()
            }
            Box(modifier = Modifier.weight(1f)) {
                when (val current = state) {
                    SessionState.Checking -> CheckingScreen()
                    is SessionState.SignedOut -> {
                        val form by viewModel.form.collectAsStateWithLifecycle()
                        LoginScreen(
                            form = form,
                            sessionReason = current.reason,
                            onHostChange = viewModel::updateHost,
                            onPasswordChange = viewModel::updatePassword,
                            onDeviceNameChange = viewModel::updateDeviceName,
                            onSubmit = viewModel::submit,
                        )
                    }

                    is SessionState.SignedIn -> {
                        val devicesOpen by viewModel.devicesOpen.collectAsStateWithLifecycle()
                        val devices by viewModel.devices.collectAsStateWithLifecycle()
                        MainShell(
                            container = container,
                            onDevices = viewModel::openDevices,
                            onSignOut = viewModel::signOut,
                        )
                        if (devicesOpen) {
                            DevicesDialog(
                                devices = devices,
                                currentDeviceId = current.credential.deviceId,
                                onDismiss = viewModel::closeDevices,
                                onRevoke = viewModel::revokeDevice,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
internal fun LanWarningBanner() {
    Surface(color = MaterialTheme.colorScheme.errorContainer) {
        Text(
            text = stringResource(R.string.lan_warning),
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 6.dp)
                .testTag("lan-warning"),
            color = MaterialTheme.colorScheme.onErrorContainer,
            style = MaterialTheme.typography.labelMedium,
        )
    }
}

@Composable
private fun CheckingScreen() {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CircularProgressIndicator(color = TroveColors.Accent, strokeWidth = 2.dp)
        Text(
            text = stringResource(R.string.login_checking),
            modifier = Modifier.padding(top = 16.dp),
            color = TroveColors.Muted,
        )
    }
}

@Composable
private fun MainShell(
    container: AppContainer,
    onDevices: () -> Unit,
    onSignOut: () -> Unit,
) {
    val backStack = rememberNavBackStack(LibraryRoute)
    val context = LocalContext.current
    val libraryViewModel: LibraryViewModel = viewModel(factory = LibraryViewModel.factory(container))
    val playerViewModel: PlayerViewModel = viewModel(factory = PlayerViewModel.factory(container))
    val transcriptViewModel: TranscriptViewModel = viewModel(
        factory = TranscriptViewModel.factory(container)
    )
    val searchViewModel: SearchViewModel = viewModel(factory = SearchViewModel.factory(container))
    val addViewModel: AddViewModel = viewModel(factory = AddViewModel.factory(container))
    val settingsViewModel: SettingsViewModel = viewModel(factory = SettingsViewModel.factory(container))
    val libraryState by libraryViewModel.state.collectAsStateWithLifecycle()
    val playerState by playerViewModel.state.collectAsStateWithLifecycle()
    val transcriptState by transcriptViewModel.state.collectAsStateWithLifecycle()
    val searchState by searchViewModel.state.collectAsStateWithLifecycle()
    val sharedUrl by container.sharedUrl.collectAsStateWithLifecycle()
    var drawerOpen by rememberSaveable { mutableStateOf(false) }
    var drawerTab by rememberSaveable { mutableStateOf(DrawerTab.LIBRARY) }

    fun root(route: NavKey) {
        backStack.clear()
        backStack.add(route)
    }

    fun openPlayer(itemId: String, autoPlay: Boolean) {
        playerViewModel.open(itemId, autoPlay)
        val last = backStack.lastOrNull()
        if (last is PlayerRoute) {
            backStack[backStack.lastIndex] = PlayerRoute(itemId)
        } else {
            backStack.add(PlayerRoute(itemId))
        }
    }

    fun openReader(
        itemId: String,
        chapterIndex: Int? = null,
        paragraphIndex: Int? = null,
        epubHref: String? = null,
        epubProgression: Double? = null,
    ) {
        context.startActivity(
            ReaderArgs(
                itemId = itemId,
                chapterIndex = chapterIndex,
                paragraphIndex = paragraphIndex,
                epubHref = epubHref,
                epubProgression = epubProgression,
            ).toIntent(context)
        )
    }

    fun openItem(itemId: String) {
        val item = libraryState.allItems.firstOrNull { it.id == itemId }
        if (item?.isBookOnly == true &&
            item.bookArtifact?.downloadState == "completed"
        ) {
            openReader(itemId)
        } else {
            openPlayer(itemId, autoPlay = false)
        }
    }

    fun openTranscript(itemId: String, focusSeq: Int? = null, query: String = "") {
        backStack.add(TranscriptRoute(itemId, focusSeq, query))
    }

    LaunchedEffect(sharedUrl) {
        val url = sharedUrl ?: return@LaunchedEffect
        addViewModel.prefill(url)
        root(AddRoute)
        container.consumeSharedUrl()
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .testTag("trove-shell"),
    ) {
        NavDisplay(
            backStack = backStack,
            transitionSpec = {
                slideInHorizontally(tween(NAV_ANIMATION_MILLIS)) { width -> width } togetherWith
                    slideOutHorizontally(tween(NAV_ANIMATION_MILLIS)) { width ->
                        -width / NAV_PARALLAX_DIVISOR
                    }
            },
            popTransitionSpec = {
                slideInHorizontally(tween(NAV_ANIMATION_MILLIS)) { width ->
                    -width / NAV_PARALLAX_DIVISOR
                } togetherWith
                    slideOutHorizontally(tween(NAV_ANIMATION_MILLIS)) { width -> width }
            },
            predictivePopTransitionSpec = {
                slideInHorizontally(tween(NAV_ANIMATION_MILLIS)) { width ->
                    -width / NAV_PARALLAX_DIVISOR
                } togetherWith
                    slideOutHorizontally(tween(NAV_ANIMATION_MILLIS)) { width -> width }
            },
            onBack = {
                when {
                    backStack.size > 1 -> backStack.removeAt(backStack.lastIndex)
                    backStack.lastOrNull() is SearchRoute ||
                        backStack.lastOrNull() is AddRoute -> root(LibraryRoute)
                }
            },
            modifier = Modifier.fillMaxSize(),
            entryProvider = entryProvider {
                entry<LibraryRoute> {
                    LibraryScreen(
                        state = libraryState,
                        selectedItemId = playerState.itemId,
                        playerState = playerState.playback,
                        transcript = playerState.transcript,
                        onRefresh = libraryViewModel::refresh,
                        onOpenItem = ::openItem,
                        onOpenCollection = { backStack.add(CollectionRoute(it)) },
                        onQuickPlay = { itemId ->
                            val item = libraryState.allItems.firstOrNull { it.id == itemId }
                            if (item?.let { it.isBookOnly } == true) {
                                openItem(itemId)
                            } else {
                                playerViewModel.open(itemId, autoPlay = true)
                            }
                        },
                        onTogglePlay = playerViewModel::toggle,
                        onSeek = playerViewModel::seekTo,
                        onSpeed = playerViewModel::setSpeed,
                        onTranscript = {
                            playerState.itemId?.let { openTranscript(it) }
                        },
                        onDownloads = { backStack.add(DownloadsRoute) },
                        onDevices = onDevices,
                        onSignOut = onSignOut,
                        onSearch = { root(SearchRoute) },
                        onAdd = { root(AddRoute) },
                        onSort = libraryViewModel::setSort,
                        onInbox = libraryViewModel::setInbox,
                        onClearFilters = libraryViewModel::clearFilters,
                        onType = libraryViewModel::setType,
                        onConsumption = libraryViewModel::setConsumption,
                        onTag = libraryViewModel::setTag,
                        onSource = libraryViewModel::setSource,
                        onSettings = { backStack.add(SettingsRoute) },
                        onDismissConflict = libraryViewModel::dismissConflict,
                        onClearCollectionActionError =
                            libraryViewModel::clearCollectionActionError,
                    )
                }
                entry<SearchRoute> {
                    SearchScreen(
                        state = searchState,
                        libraryItems = libraryState.allItems,
                        onBack = { root(LibraryRoute) },
                        onQuery = searchViewModel::updateQuery,
                        onFilters = searchViewModel::setFilters,
                        onClearFilters = searchViewModel::clearFilters,
                        onOpenItem = ::openItem,
                        onOpenTranscript = ::openTranscript,
                        onOpenBook = { itemId, chapter, paragraph ->
                            val item = libraryState.allItems.firstOrNull { it.id == itemId }
                            if (item?.bookArtifact?.downloadState == "completed") {
                                openReader(
                                    itemId,
                                    chapterIndex = chapter,
                                    paragraphIndex = paragraph,
                                )
                            } else {
                                openItem(itemId)
                            }
                        },
                        onLibrary = { root(LibraryRoute) },
                        onAdd = { root(AddRoute) },
                    )
                }
                entry<AddRoute> {
                    AddScreen(
                        viewModel = addViewModel,
                        onBack = { root(LibraryRoute) },
                        onLibrary = { root(LibraryRoute) },
                        onSearch = { root(SearchRoute) },
                        onOpenItem = ::openItem,
                        onOpenCollection = { backStack.add(CollectionRoute(it)) },
                    )
                }
                entry<SettingsRoute> {
                    SettingsScreen(
                        viewModel = settingsViewModel,
                        onBack = { backStack.removeAt(backStack.lastIndex) },
                        onDownloads = { backStack.add(DownloadsRoute) },
                    )
                }
                entry<DownloadsRoute> {
                    DownloadsScreen(
                        state = libraryState,
                        onBack = { backStack.removeAt(backStack.lastIndex) },
                        onPause = libraryViewModel::pauseDownload,
                        onRetry = libraryViewModel::retryDownload,
                        onRemove = libraryViewModel::removeDownload,
                        onAllowMetered = libraryViewModel::setAllowMetered,
                        onChargingOnly = libraryViewModel::setChargingOnly,
                        onQuota = libraryViewModel::setQuotaBytes,
                    )
                }
                entry<CollectionRoute> { route ->
                    CollectionScreen(
                        collectionId = route.collectionId,
                        items = libraryState.allItems,
                        actionError = libraryState.collectionActionError,
                        playerState = playerState.playback,
                        onClearError = libraryViewModel::clearCollectionActionError,
                        onBack = { backStack.removeAt(backStack.lastIndex) },
                        onOpenItem = ::openItem,
                        onPlayItem = { playerViewModel.open(it, autoPlay = true) },
                        onTogglePlay = playerViewModel::toggle,
                        onRetryItem = libraryViewModel::retryCollectionItem,
                        onRetryFailed = {
                            libraryViewModel.retryCollectionFailed(route.collectionId)
                        },
                        onDownloadAll = {
                            libraryViewModel.downloadCollection(route.collectionId)
                        },
                        autoDownload = route.collectionId in libraryState.autoDownloadCollections,
                        onStopAutoDownload = {
                            libraryViewModel.disableCollectionAutoDownload(route.collectionId)
                        },
                        onDelete = { mode ->
                            libraryViewModel.deleteCollection(route.collectionId, mode)
                            if (backStack.lastOrNull() is CollectionRoute) {
                                backStack.removeAt(backStack.lastIndex)
                            }
                        },
                    )
                }
                entry<PlayerRoute> { route ->
                    LaunchedEffect(route.itemId) {
                        playerViewModel.open(route.itemId, autoPlay = false)
                    }
                    PlayerScreen(
                        state = playerState,
                        onBack = { backStack.removeAt(backStack.lastIndex) },
                        onToggle = playerViewModel::toggle,
                        onSeek = playerViewModel::seekTo,
                        onSeekBy = playerViewModel::seekBy,
                        onSpeed = playerViewModel::setSpeed,
                        onDownload = playerViewModel::download,
                        onPauseDownload = playerViewModel::pauseDownload,
                        onRetryDownload = playerViewModel::retryDownload,
                        onRemoveDownload = playerViewModel::removeDownload,
                        onDelete = playerViewModel::deleteItem,
                        onTranscript = { openTranscript(route.itemId) },
                        onRefreshTranscript = playerViewModel::refreshTranscript,
                        onOpenDrawer = {
                            drawerTab = DrawerTab.LIBRARY
                            drawerOpen = true
                        },
                        onTags = playerViewModel::replaceTags,
                        onConsumption = playerViewModel::setConsumption,
                        onClearTagError = playerViewModel::clearTagError,
                        onRead = { openReader(it) },
                        onRetryProcessing = playerViewModel::retryProcessing,
                    )
                }
                entry<TranscriptRoute> { route ->
                    LaunchedEffect(route.itemId, route.focusSeq, route.query) {
                        transcriptViewModel.open(route.itemId, route.focusSeq, route.query)
                    }
                    TranscriptScreen(
                        state = transcriptState,
                        playback = playerState.playback,
                        onBack = { backStack.removeAt(backStack.lastIndex) },
                        onQuery = transcriptViewModel::updateQuery,
                        onRetry = transcriptViewModel::retry,
                    )
                }
            },
        )
        TroveDrawer(
            open = drawerOpen,
            tab = drawerTab,
            state = libraryState,
            onTab = { drawerTab = it },
            onClose = { drawerOpen = false },
            onOpenItem = { itemId ->
                drawerOpen = false
                openItem(itemId)
            },
            onInbox = libraryViewModel::setInbox,
            onConsumption = libraryViewModel::setConsumption,
            onAdd = {
                drawerOpen = false
                root(AddRoute)
            },
            onSearch = {
                drawerOpen = false
                root(SearchRoute)
            },
            onDownloads = {
                drawerOpen = false
                backStack.add(DownloadsRoute)
            },
            onSettings = {
                drawerOpen = false
                backStack.add(SettingsRoute)
            },
            onDevices = {
                drawerOpen = false
                onDevices()
            },
            onSignOut = {
                drawerOpen = false
                onSignOut()
            },
        )
    }
}

@Composable
private fun DevicesDialog(
    devices: List<DeviceDto>,
    currentDeviceId: String,
    onDismiss: () -> Unit,
    onRevoke: (String) -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = TroveColors.Paper2,
        title = { Text(stringResource(R.string.login_devices)) },
        text = {
            LazyColumn {
                items(devices, key = { it.deviceId }) { device ->
                    Column(modifier = Modifier.padding(vertical = 8.dp)) {
                        val suffix = if (device.deviceId == currentDeviceId) {
                            " · ${stringResource(R.string.login_this_device)}"
                        } else {
                            ""
                        }
                        Text("${device.name}$suffix")
                        if (device.revokedAt != null) {
                            Text(
                                text = stringResource(R.string.login_revoked),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        } else {
                            TextButton(onClick = { onRevoke(device.deviceId) }) {
                                Text(stringResource(R.string.login_revoke))
                            }
                        }
                        HorizontalDivider(color = TroveColors.Line)
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text(stringResource(R.string.login_close))
            }
        },
    )
}
