package dev.trove.app.session

import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.FakeTroveApi
import dev.trove.app.testing.FakeTroveApiFactory
import dev.trove.core.auth.StoredCredential
import dev.trove.core.network.HealthDto
import dev.trove.core.network.TroveApiException
import dev.trove.core.network.TroveNetworkException
import dev.trove.core.network.TroveTlsException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class SessionControllerTest {
    @Test
    fun restoreUsesPersistedHostAndToken() = runTest {
        val tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel"))
        val settingsStore = FakeSettingsStore("https://host.example")
        val controller = SessionController(
            tokenStore, settingsStore, FakeTroveApiFactory(FakeTroveApi()),
            allowDebugCleartext = false, scope = this,
        )
        controller.restore()
        val state = controller.state.value as SessionState.SignedIn
        assertEquals("https://host.example", state.hostUrl)
        assertEquals("token", state.credential.token)
    }

    @Test
    fun successfulLoginPersistsHostAndToken() = runTest {
        val tokenStore = FakeTokenStore()
        val settingsStore = FakeSettingsStore()
        val controller = SessionController(
            tokenStore = tokenStore,
            settingsStore = settingsStore,
            apiFactory = FakeTroveApiFactory(FakeTroveApi()),
            allowDebugCleartext = false,
            scope = this,
        )
        val outcome = controller.login("https://Host.example/", "pw", "Pixel")
        assertNull(outcome.error)
        assertEquals("https://host.example", settingsStore.current)
        assertEquals("test-token", tokenStore.credential?.token)
        val state = controller.state.value as SessionState.SignedIn
        assertEquals("https://host.example", state.hostUrl)
    }

    @Test
    fun cleartextHostIsRejectedBeforeNetwork() = runTest {
        val factory = FakeTroveApiFactory(FakeTroveApi())
        val controller = SessionController(
            FakeTokenStore(), FakeSettingsStore(), factory,
            allowDebugCleartext = false, scope = this,
        )
        val outcome = controller.login("http://192.168.1.10:8765", "pw", "Pixel")
        assertEquals(SessionError.CLEARTEXT_HOST, outcome.error)
        assertTrue(factory.requests.isEmpty())
    }

    @Test
    fun debugBuildAllowsLoopbackCleartext() = runTest {
        val factory = FakeTroveApiFactory(FakeTroveApi())
        val controller = SessionController(
            FakeTokenStore(), FakeSettingsStore(), factory,
            allowDebugCleartext = true, scope = this,
        )
        val outcome = controller.login("http://localhost:8765/", "pw", "Pixel")
        assertNull(outcome.error)
        assertEquals("http://localhost:8765", factory.requests.single().first)
    }

    @Test
    fun lanBuildAllowsPrivateCleartextHost() = runTest {
        val factory = FakeTroveApiFactory(FakeTroveApi())
        val controller = SessionController(
            FakeTokenStore(), FakeSettingsStore(), factory,
            allowDebugCleartext = true,
            allowLanCleartext = true,
            scope = this,
        )
        val outcome = controller.login("http://192.168.1.10:8765/", "pw", "Pixel")
        assertNull(outcome.error)
        assertEquals("http://192.168.1.10:8765", factory.requests.single().first)
    }

    @Test
    fun wrongPasswordIsReported() = runTest {
        val api = FakeTroveApi().apply {
            tokenError = TroveApiException("auth.invalid", "Incorrect password", 401)
        }
        val controller = SessionController(
            FakeTokenStore(), FakeSettingsStore(), FakeTroveApiFactory(api),
            allowDebugCleartext = false, scope = this,
        )
        assertEquals(SessionError.INVALID_PASSWORD, controller.login("https://host.example", "bad", "Pixel").error)
    }

    @Test
    fun rateLimitCarriesRetryAfter() = runTest {
        val api = FakeTroveApi().apply {
            tokenError = TroveApiException(
                "auth.rate_limited", "Too many", 429, retryAfterSeconds = 30,
            )
        }
        val controller = SessionController(
            FakeTokenStore(), FakeSettingsStore(), FakeTroveApiFactory(api),
            allowDebugCleartext = false, scope = this,
        )
        val outcome = controller.login("https://host.example", "pw", "Pixel")
        assertEquals(SessionError.RATE_LIMITED, outcome.error)
        assertEquals(30L, outcome.retryAfterSeconds)
    }

    @Test
    fun offlineAndTlsErrorsHaveDistinctStates() = runTest {
        val offline = FakeTroveApi().apply { healthError = TroveNetworkException("offline") }
        val offlineController = SessionController(
            FakeTokenStore(), FakeSettingsStore(), FakeTroveApiFactory(offline),
            allowDebugCleartext = false, scope = this,
        )
        assertEquals(
            SessionError.HOST_OFFLINE,
            offlineController.login("https://host.example", "pw", "Pixel").error,
        )

        val tls = FakeTroveApi().apply { healthError = TroveTlsException("tls") }
        val tlsController = SessionController(
            FakeTokenStore(), FakeSettingsStore(), FakeTroveApiFactory(tls),
            allowDebugCleartext = false, scope = this,
        )
        assertEquals(
            SessionError.TLS,
            tlsController.login("https://host.example", "pw", "Pixel").error,
        )
    }

    @Test
    fun incompatibleHostIsRejected() = runTest {
        val api = FakeTroveApi().apply {
            healthResponse = HealthDto("old", mapOf("sync" to false))
        }
        val controller = SessionController(
            FakeTokenStore(), FakeSettingsStore(), FakeTroveApiFactory(api),
            allowDebugCleartext = false, scope = this,
        )
        assertEquals(
            SessionError.HOST_INCOMPATIBLE,
            controller.login("https://host.example", "pw", "Pixel").error,
        )
    }

    @Test
    fun unauthorizedClearsTokenAndKeepsHost() = runTest {
        val tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel"))
        val settingsStore = FakeSettingsStore("https://host.example")
        val controller = SessionController(
            tokenStore, settingsStore, FakeTroveApiFactory(FakeTroveApi()),
            allowDebugCleartext = false, scope = this,
        )
        controller.restore()
        controller.onUnauthorized("auth.device_revoked")
        advanceUntilIdle()
        assertNull(tokenStore.credential)
        val state = controller.state.value as SessionState.SignedOut
        assertEquals("https://host.example", state.hostUrl)
        assertEquals(SessionError.DEVICE_REVOKED, state.reason)
    }

    @Test
    fun logoutRevokesCurrentDeviceAndClearsToken() = runTest {
        val tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel"))
        val settingsStore = FakeSettingsStore("https://host.example")
        val api = FakeTroveApi()
        val controller = SessionController(
            tokenStore, settingsStore, FakeTroveApiFactory(api),
            allowDebugCleartext = false, scope = this,
        )
        controller.restore()
        controller.logout()
        assertEquals(listOf("device-1"), api.revokedDevices)
        assertNull(tokenStore.credential)
        assertEquals("https://host.example", (controller.state.value as SessionState.SignedOut).hostUrl)
    }

    @Test
    fun devicesComeFromHost() = runTest {
        val tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel"))
        val api = FakeTroveApi()
        val controller = SessionController(
            tokenStore, FakeSettingsStore("https://host.example"),
            FakeTroveApiFactory(api),
            allowDebugCleartext = false, scope = this,
        )
        controller.restore()
        val devices = controller.devices()
        assertEquals(listOf("device-1"), devices.map { it.deviceId })
    }

    @Test
    fun revokingCurrentDeviceSignsOut() = runTest {
        val tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel"))
        val controller = SessionController(
            tokenStore, FakeSettingsStore("https://host.example"),
            FakeTroveApiFactory(FakeTroveApi()),
            allowDebugCleartext = false, scope = this,
        )
        controller.restore()
        controller.revokeDevice("device-1")
        assertNull(tokenStore.credential)
        assertTrue(controller.state.value is SessionState.SignedOut)
    }
}
