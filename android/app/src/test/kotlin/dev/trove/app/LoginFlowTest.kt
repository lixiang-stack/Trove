package dev.trove.app

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.session.SessionViewModel
import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.FakeTroveApi
import dev.trove.app.testing.testHarness
import dev.trove.core.auth.StoredCredential
import dev.trove.core.network.TroveApiException
import dev.trove.core.network.TroveNetworkException
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class LoginFlowTest {
    @get:Rule
    val compose = createComposeRule()

    private fun waitForTag(tag: String) {
        compose.waitUntil(5_000) {
            compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
        }
    }

    private fun fillForm(host: String = "https://host.example") {
        waitForTag("host-url")
        compose.onNodeWithTag("host-url").performTextInput(host)
        compose.onNodeWithTag("password").performTextInput("pw")
        compose.onNodeWithTag("device-name").performTextClearance()
        compose.onNodeWithTag("device-name").performTextInput("Pixel")
        compose.onNodeWithTag("login-submit").performClick()
    }

    @Test
    fun successfulLoginEntersShellAndPersistsToken() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = testHarness(context)
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel) }

        fillForm()

        waitForTag("trove-shell")
        compose.onNodeWithText("Library 尚未接入").assertIsDisplayed()
        assertEquals("test-token", harness.tokenStore.credential?.token)
        assertEquals("https://host.example", harness.settingsStore.current)
    }

    @Test
    fun wrongPasswordShowsReadableError() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val api = FakeTroveApi().apply {
            tokenError = TroveApiException("auth.invalid", "Incorrect password", 401)
        }
        val harness = testHarness(context, api = api)
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel) }

        fillForm()

        waitForTag("login-error")
        compose.onNodeWithText("密码错误").assertExists()
    }

    @Test
    fun offlineHostShowsReadableError() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val api = FakeTroveApi().apply { healthError = TroveNetworkException("offline") }
        val harness = testHarness(context, api = api)
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel) }

        fillForm()

        waitForTag("login-error")
        compose.onNodeWithText("无法连接 Host，请检查地址和网络").assertExists()
    }

    @Test
    fun cleartextHostIsRejectedInReleaseBuild() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = testHarness(context, allowDebugCleartext = false)
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel) }

        fillForm(host = "http://192.168.1.10:8765")

        waitForTag("login-error")
        compose.onNodeWithText("正式版本只允许 HTTPS Host").assertExists()
        assertEquals(0, harness.apiFactory.requests.size)
    }

    @Test
    fun persistedTokenRestoresShellWithoutLogin() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = testHarness(
            context,
            tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel")),
            settingsStore = FakeSettingsStore("https://host.example"),
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel) }

        waitForTag("trove-shell")
        compose.onNodeWithText("Library 尚未接入").assertIsDisplayed()
    }

    @Test
    fun revokedTokenReturnsToLogin() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = testHarness(
            context,
            tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel")),
            settingsStore = FakeSettingsStore("https://host.example"),
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel) }
        waitForTag("trove-shell")

        harness.container.sessionController.onUnauthorized("auth.device_revoked")

        compose.waitUntil(5_000) {
            compose.onAllNodesWithText("登录已失效，请重新登录")
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("登录已失效，请重新登录").assertExists()
        compose.onNodeWithTag("host-url").assertIsDisplayed()
    }

    @Test
    fun logoutRevokesCurrentDevice() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = testHarness(
            context,
            tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel")),
            settingsStore = FakeSettingsStore("https://host.example"),
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel) }
        waitForTag("trove-shell")

        compose.onNodeWithText("退出登录").performClick()

        waitForTag("host-url")
        assertEquals(listOf("device-1"), harness.api.revokedDevices)
        assertEquals(null, harness.tokenStore.credential)
    }
}
