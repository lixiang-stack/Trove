package dev.trove.app

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.session.SessionViewModel
import dev.trove.app.testing.testHarness
import dev.trove.app.testing.waitForTag
import org.junit.Assert.assertNotNull
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class AppSmokeTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    fun applicationBootsContainer() {
        val application = RuntimeEnvironment.getApplication() as TroveApplication
        assertNotNull(application.container)
    }

    @Test
    fun loginScreenIsShownWhenSignedOut() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = testHarness(context)
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }
        waitForTag(compose, "host-url")
        compose.onNodeWithTag("host-url").assertIsDisplayed()
        compose.onNodeWithText("连接 Host").assertIsDisplayed()
    }

    @Test
    fun lanWarningBannerIsVisible() {
        compose.setContent {
            dev.trove.app.ui.theme.TroveTheme {
                LanWarningBanner()
            }
        }
        compose.onNodeWithTag("lan-warning").assertIsDisplayed()
        compose.onNodeWithText("LAN 调试版", substring = true).assertIsDisplayed()
    }
}
