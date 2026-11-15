package dev.trove.app

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.annotation.StringRes
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import dev.trove.app.session.LoginScreen
import dev.trove.app.session.SessionState
import dev.trove.app.session.SessionViewModel
import dev.trove.app.ui.theme.TroveTheme
import dev.trove.core.network.DeviceDto

private data class Destination(
    @StringRes val label: Int,
    val glyph: String,
    @StringRes val placeholder: Int,
)

private val destinations = listOf(
    Destination(R.string.nav_library, "书", R.string.nav_library_placeholder),
    Destination(R.string.nav_search, "搜", R.string.nav_search_placeholder),
    Destination(R.string.nav_add, "加", R.string.nav_add_placeholder),
)

@Composable
fun TroveApp(viewModel: SessionViewModel) {
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
        CircularProgressIndicator()
        Text(
            text = stringResource(R.string.login_checking),
            modifier = Modifier.padding(top = 16.dp),
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MainShell(
    onDevices: () -> Unit,
    onSignOut: () -> Unit,
) {
    var selected by rememberSaveable { mutableIntStateOf(0) }
    Scaffold(
        modifier = Modifier.testTag("trove-shell"),
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.app_name)) },
                actions = {
                    TextButton(onClick = onDevices) {
                        Text(stringResource(R.string.login_devices))
                    }
                    TextButton(onClick = onSignOut) {
                        Text(stringResource(R.string.login_sign_out))
                    }
                },
            )
        },
        bottomBar = {
            NavigationBar {
                destinations.forEachIndexed { index, destination ->
                    NavigationBarItem(
                        selected = selected == index,
                        onClick = { selected = index },
                        icon = { Text(destination.glyph) },
                        label = { Text(stringResource(destination.label)) },
                    )
                }
            }
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = stringResource(destinations[selected].label),
                style = MaterialTheme.typography.headlineMedium,
            )
            Text(
                text = stringResource(destinations[selected].placeholder),
                style = MaterialTheme.typography.bodyMedium,
            )
        }
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
                        HorizontalDivider()
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
