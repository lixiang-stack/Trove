package dev.trove.app.session

import android.os.Build
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import dev.trove.core.network.DeviceDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

private const val DEFAULT_DEVICE_NAME = "Android"

data class LoginForm(
    val hostUrl: String = "",
    val password: String = "",
    val deviceName: String = Build.MODEL.ifBlank { DEFAULT_DEVICE_NAME },
    val submitting: Boolean = false,
    val error: SessionError? = null,
    val retryAfterSeconds: Long? = null,
)

class SessionViewModel(private val controller: SessionController) : ViewModel() {
    val session: StateFlow<SessionState> = controller.state

    private val _form = MutableStateFlow(LoginForm())
    val form: StateFlow<LoginForm> = _form.asStateFlow()

    private val _devices = MutableStateFlow<List<DeviceDto>>(emptyList())
    val devices: StateFlow<List<DeviceDto>> = _devices.asStateFlow()

    private val _devicesOpen = MutableStateFlow(false)
    val devicesOpen: StateFlow<Boolean> = _devicesOpen.asStateFlow()

    init {
        viewModelScope.launch {
            controller.restore()
            (controller.state.value as? SessionState.SignedOut)?.let { signedOut ->
                if (signedOut.hostUrl.isNotBlank()) {
                    _form.update { it.copy(hostUrl = signedOut.hostUrl) }
                }
            }
        }
    }

    fun updateHost(value: String) {
        _form.update { it.copy(hostUrl = value, error = null) }
    }

    fun updatePassword(value: String) {
        _form.update { it.copy(password = value, error = null) }
    }

    fun updateDeviceName(value: String) {
        _form.update { it.copy(deviceName = value, error = null) }
    }

    fun submit() {
        val current = _form.value
        if (current.submitting) {
            return
        }
        _form.update { it.copy(submitting = true, error = null, retryAfterSeconds = null) }
        viewModelScope.launch {
            val outcome = controller.login(
                rawHost = current.hostUrl,
                password = current.password,
                deviceName = current.deviceName.ifBlank { DEFAULT_DEVICE_NAME },
            )
            _form.update {
                it.copy(
                    submitting = false,
                    error = outcome.error,
                    retryAfterSeconds = outcome.retryAfterSeconds,
                    password = if (outcome.error == null) "" else it.password,
                )
            }
        }
    }

    fun signOut() {
        viewModelScope.launch {
            controller.logout()
            _form.update {
                LoginForm(hostUrl = (controller.state.value as? SessionState.SignedOut)?.hostUrl.orEmpty())
            }
        }
    }

    fun openDevices() {
        _devicesOpen.value = true
        viewModelScope.launch {
            runCatching { controller.devices() }
                .onSuccess { _devices.value = it }
        }
    }

    fun closeDevices() {
        _devicesOpen.value = false
    }

    fun revokeDevice(deviceId: String) {
        viewModelScope.launch {
            runCatching { controller.revokeDevice(deviceId) }
            runCatching { controller.devices() }
                .onSuccess { _devices.value = it }
        }
    }

    companion object {
        fun factory(controller: SessionController): ViewModelProvider.Factory =
            viewModelFactory {
                initializer { SessionViewModel(controller) }
            }
    }
}
