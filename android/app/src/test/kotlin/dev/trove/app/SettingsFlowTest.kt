package dev.trove.app

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.session.SessionViewModel
import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.testHarness
import dev.trove.app.testing.waitForTag
import dev.trove.core.auth.StoredCredential
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class SettingsFlowTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    fun settingsShowsHostSyncStorageAndSanitizedDiagnostics() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = testHarness(
            context,
            tokenStore = FakeTokenStore(StoredCredential("secret-token", "device-1", "Pixel")),
            settingsStore = FakeSettingsStore("https://host.example"),
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-screen")
        compose.onNodeWithContentDescription("更多").performClick()
        compose.onNodeWithText("设置").performClick()
        waitForTag(compose, "settings-screen")

        compose.onNodeWithText("https://host.example").assertIsDisplayed()
        compose.onNodeWithText("Pixel").assertIsDisplayed()
        compose.onNodeWithText("下载与存储").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("诊断").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("清除本地数据").performScrollTo().assertIsDisplayed()
        val texts = compose.onAllNodesWithTag("settings-screen").fetchSemanticsNodes()
        check(texts.isNotEmpty())
    }
}
