package dev.trove.app.session

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import dev.trove.app.R

@Composable
fun LoginScreen(
    form: LoginForm,
    sessionReason: SessionError?,
    onHostChange: (String) -> Unit,
    onPasswordChange: (String) -> Unit,
    onDeviceNameChange: (String) -> Unit,
    onSubmit: () -> Unit,
) {
    val error = form.error ?: sessionReason
    Scaffold { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 24.dp, vertical = 32.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = stringResource(R.string.login_title),
                style = MaterialTheme.typography.headlineMedium,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = stringResource(R.string.login_subtitle),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(24.dp))
            OutlinedTextField(
                value = form.hostUrl,
                onValueChange = onHostChange,
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag("host-url"),
                label = { Text(stringResource(R.string.login_host)) },
                placeholder = { Text("https://trove.example.ts.net") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Uri,
                    imeAction = ImeAction.Next,
                ),
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = form.password,
                onValueChange = onPasswordChange,
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag("password"),
                label = { Text(stringResource(R.string.login_password)) },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Password,
                    imeAction = ImeAction.Next,
                ),
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = form.deviceName,
                onValueChange = onDeviceNameChange,
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag("device-name"),
                label = { Text(stringResource(R.string.login_device_name)) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            )
            Spacer(Modifier.height(24.dp))
            if (error != null) {
                Text(
                    text = sessionErrorText(error, form.retryAfterSeconds),
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("login-error"),
                )
                Spacer(Modifier.height(16.dp))
            }
            Button(
                onClick = onSubmit,
                enabled = !form.submitting,
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag("login-submit"),
            ) {
                if (form.submitting) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.Center,
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            strokeWidth = 2.dp,
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(stringResource(R.string.login_connecting))
                    }
                } else {
                    Text(stringResource(R.string.login_connect))
                }
            }
        }
    }
}

@Composable
fun sessionErrorText(error: SessionError, retryAfterSeconds: Long?): String = when (error) {
    SessionError.EMPTY_HOST -> stringResource(R.string.error_empty_host)
    SessionError.INVALID_HOST -> stringResource(R.string.error_invalid_host)
    SessionError.CLEARTEXT_HOST -> stringResource(R.string.error_cleartext_host)
    SessionError.UNSUPPORTED_PATH -> stringResource(R.string.error_unsupported_path)
    SessionError.INVALID_PASSWORD -> stringResource(R.string.error_invalid_password)
    SessionError.RATE_LIMITED -> if (retryAfterSeconds != null) {
        stringResource(R.string.error_rate_limited_seconds, retryAfterSeconds)
    } else {
        stringResource(R.string.error_rate_limited)
    }

    SessionError.HOST_OFFLINE -> stringResource(R.string.error_host_offline)
    SessionError.TLS -> stringResource(R.string.error_tls)
    SessionError.HOST_INCOMPATIBLE -> stringResource(R.string.error_host_incompatible)
    SessionError.DEVICE_REVOKED -> stringResource(R.string.error_device_revoked)
    SessionError.UNKNOWN -> stringResource(R.string.error_unknown)
}
