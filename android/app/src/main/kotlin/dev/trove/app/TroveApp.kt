package dev.trove.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation3.runtime.NavKey
import androidx.navigation3.runtime.entryProvider
import androidx.navigation3.runtime.rememberNavBackStack
import androidx.navigation3.ui.NavDisplay
import dev.trove.app.add.AddScreen
import dev.trove.app.download.DownloadsScreen
import dev.trove.app.library.LibraryScreen
import dev.trove.app.library.LibraryViewModel
import dev.trove.app.player.PlayerScreen
import dev.trove.app.player.PlayerViewModel
import dev.trove.app.search.SearchScreen
import dev.trove.app.session.LoginScreen
import dev.trove.app.session.SessionState
import dev.trove.app.session.SessionViewModel
import dev.trove.app.transcript.TranscriptScreen
import dev.trove.app.transcript.TranscriptViewModel
import dev.trove.app.ui.components.DrawerTab
import dev.trove.app.ui.components.TroveDrawer
import dev.trove.app.ui.theme.TroveColors
import dev.trove.app.ui.theme.TroveTheme
import dev.trove.core.network.DeviceDto
import kotlinx.serialization.Serializable

@Serializable
data object LibraryRoute : NavKey

@Serializable
data object SearchRoute : NavKey

@Serializable
data object AddRoute : NavKey

@Serializable
data class PlayerRoute(val itemId: String) : NavKey

@Serializable
data class TranscriptRoute(val itemId: String) : NavKey

@Serializable
data object DownloadsRoute : NavKey

@Composable
fun TroveApp(viewModel: SessionViewModel, container: AppContainer) {
    TroveTheme {
        val state by viewModel.session.collectAsStateWithLifecycle()
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
    val libraryViewModel: LibraryViewModel = viewModel(factory = LibraryViewModel.factory(container))
    val playerViewModel: PlayerViewModel = viewModel(factory = PlayerViewModel.factory(container))
    val transcriptViewModel: TranscriptViewModel = viewModel(
        factory = TranscriptViewModel.factory(container)
    )
    val libraryState by libraryViewModel.state.collectAsStateWithLifecycle()
    val playerState by playerViewModel.state.collectAsStateWithLifecycle()
    val transcriptState by transcriptViewModel.state.collectAsStateWithLifecycle()
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

    Box(
        modifier = Modifier
            .fillMaxSize()
            .testTag("trove-shell"),
    ) {
        NavDisplay(
            backStack = backStack,
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
                        onOpenItem = { openPlayer(it, autoPlay = false) },
                        onQuickPlay = { itemId ->
                            val item = libraryState.allItems.firstOrNull { it.id == itemId }
                            if (item?.let { it.hasBook && !it.hasAudio } == true) {
                                openPlayer(itemId, autoPlay = false)
                            } else {
                                playerViewModel.open(itemId, autoPlay = true)
                            }
                        },
                        onTogglePlay = playerViewModel::toggle,
                        onSeek = playerViewModel::seekTo,
                        onSpeed = playerViewModel::setSpeed,
                        onTranscript = {
                            playerState.itemId?.let { backStack.add(TranscriptRoute(it)) }
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
                    )
                }
                entry<SearchRoute> {
                    SearchScreen(
                        items = libraryState.allItems,
                        onBack = { root(LibraryRoute) },
                        onOpenItem = { openPlayer(it, autoPlay = false) },
                        onLibrary = { root(LibraryRoute) },
                        onAdd = { root(AddRoute) },
                    )
                }
                entry<AddRoute> {
                    AddScreen(
                        onBack = { root(LibraryRoute) },
                        onLibrary = { root(LibraryRoute) },
                        onSearch = { root(SearchRoute) },
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
                        onTranscript = { backStack.add(TranscriptRoute(route.itemId)) },
                        onRefreshTranscript = playerViewModel::refreshTranscript,
                        onOpenDrawer = {
                            drawerTab = DrawerTab.LIBRARY
                            drawerOpen = true
                        },
                    )
                }
                entry<TranscriptRoute> { route ->
                    LaunchedEffect(route.itemId) {
                        transcriptViewModel.open(route.itemId)
                    }
                    TranscriptScreen(
                        state = transcriptState,
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
                openPlayer(itemId, autoPlay = false)
            },
            onInbox = libraryViewModel::setInbox,
            onConsumption = libraryViewModel::setConsumption,
            onAdd = {
                drawerOpen = false
                root(AddRoute)
            },
            onDownloads = {
                drawerOpen = false
                backStack.add(DownloadsRoute)
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
