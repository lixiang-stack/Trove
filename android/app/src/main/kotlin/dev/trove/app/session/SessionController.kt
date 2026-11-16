package dev.trove.app.session

import dev.trove.core.auth.HostUrl
import dev.trove.core.auth.HostUrlError
import dev.trove.core.auth.HostUrlResult
import dev.trove.core.auth.StoredCredential
import dev.trove.core.auth.TokenStore
import dev.trove.core.network.DeviceDto
import dev.trove.core.network.HealthDto
import dev.trove.core.network.RetrofitTroveApiFactory
import dev.trove.core.network.TroveApiException
import dev.trove.core.network.TroveApiFactory
import dev.trove.core.network.TroveClient
import dev.trove.core.network.TroveNetworkException
import dev.trove.core.network.TroveTlsException
import dev.trove.core.network.UnauthorizedListener
import dev.trove.core.settings.SettingsStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

sealed interface SessionState {
    data object Checking : SessionState

    data class SignedOut(
        val hostUrl: String,
        val reason: SessionError? = null,
    ) : SessionState

    data class SignedIn(
        val hostUrl: String,
        val credential: StoredCredential,
    ) : SessionState
}

enum class SessionError {
    EMPTY_HOST,
    INVALID_HOST,
    CLEARTEXT_HOST,
    UNSUPPORTED_PATH,
    INVALID_PASSWORD,
    RATE_LIMITED,
    HOST_OFFLINE,
    TLS,
    HOST_INCOMPATIBLE,
    DEVICE_REVOKED,
    UNKNOWN,
}

data class LoginOutcome(
    val error: SessionError? = null,
    val retryAfterSeconds: Long? = null,
)

class SessionController(
    private val tokenStore: TokenStore,
    private val settingsStore: SettingsStore,
    private val apiFactory: TroveApiFactory = RetrofitTroveApiFactory(),
    private val allowDebugCleartext: Boolean,
    private val allowLanCleartext: Boolean = false,
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO),
) : UnauthorizedListener {
    private val _state = MutableStateFlow<SessionState>(SessionState.Checking)
    val state: StateFlow<SessionState> = _state.asStateFlow()

    suspend fun restore() {
        val hostUrl = settingsStore.hostUrl.first().orEmpty()
        val credential = tokenStore.read()
        _state.value = if (credential != null && hostUrl.isNotBlank()) {
            SessionState.SignedIn(hostUrl, credential)
        } else {
            SessionState.SignedOut(hostUrl)
        }
    }

    suspend fun login(rawHost: String, password: String, deviceName: String): LoginOutcome {
        val normalized = when (
            val result = HostUrl.normalize(rawHost, allowDebugCleartext, allowLanCleartext)
        ) {
            is HostUrlResult.Invalid -> return LoginOutcome(error = result.reason.toSessionError())
            is HostUrlResult.Valid -> result.baseUrl
        }
        val client = TroveClient(apiFactory.create(normalized, null))
        return try {
            val health = client.health()
            if (health.capabilities["device_tokens"] != true || health.capabilities["sync"] != true) {
                return LoginOutcome(error = SessionError.HOST_INCOMPATIBLE)
            }
            val issued = client.deviceToken(password = password, name = deviceName.trim())
            val credential = StoredCredential(
                token = issued.token,
                deviceId = issued.deviceId,
                deviceName = issued.name,
            )
            settingsStore.saveHostUrl(normalized)
            tokenStore.save(credential)
            _state.value = SessionState.SignedIn(normalized, credential)
            LoginOutcome()
        } catch (error: TroveApiException) {
            when {
                error.statusCode == 401 || error.statusCode == 403 ->
                    LoginOutcome(error = SessionError.INVALID_PASSWORD)

                error.statusCode == 429 -> LoginOutcome(
                    error = SessionError.RATE_LIMITED,
                    retryAfterSeconds = error.retryAfterSeconds,
                )

                else -> LoginOutcome(error = SessionError.UNKNOWN)
            }
        } catch (_: TroveTlsException) {
            LoginOutcome(error = SessionError.TLS)
        } catch (_: TroveNetworkException) {
            LoginOutcome(error = SessionError.HOST_OFFLINE)
        }
    }

    suspend fun logout() {
        val current = _state.value
        if (current is SessionState.SignedIn) {
            runCatching {
                authenticatedClient(current).revokeDevice(current.credential.deviceId)
            }
            tokenStore.clear()
            _state.value = SessionState.SignedOut(current.hostUrl)
        }
    }

    suspend fun devices(): List<DeviceDto> {
        val current = _state.value as? SessionState.SignedIn ?: return emptyList()
        return authenticatedClient(current).devices().devices
    }

    suspend fun health(): HealthDto? =
        currentClient()?.let { runCatching { it.health() }.getOrNull() }

    suspend fun revokeDevice(deviceId: String) {
        val current = _state.value as? SessionState.SignedIn ?: return
        authenticatedClient(current).revokeDevice(deviceId)
        if (deviceId == current.credential.deviceId) {
            tokenStore.clear()
            _state.value = SessionState.SignedOut(current.hostUrl)
        }
    }

    fun currentClient(): TroveClient? =
        (_state.value as? SessionState.SignedIn)?.let(::authenticatedClient)

    override fun onUnauthorized(code: String) {
        scope.launch {
            val current = _state.value
            tokenStore.clear()
            if (current is SessionState.SignedIn) {
                _state.value = SessionState.SignedOut(
                    hostUrl = current.hostUrl,
                    reason = SessionError.DEVICE_REVOKED,
                )
            }
        }
    }

    private fun authenticatedClient(session: SessionState.SignedIn): TroveClient =
        TroveClient(apiFactory.create(session.hostUrl, session.credential.token), this)

    private fun HostUrlError.toSessionError(): SessionError = when (this) {
        HostUrlError.EMPTY -> SessionError.EMPTY_HOST
        HostUrlError.INVALID -> SessionError.INVALID_HOST
        HostUrlError.CLEARTEXT -> SessionError.CLEARTEXT_HOST
        HostUrlError.UNSUPPORTED_PATH -> SessionError.UNSUPPORTED_PATH
    }
}
