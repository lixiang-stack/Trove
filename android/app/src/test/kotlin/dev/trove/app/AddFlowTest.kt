package dev.trove.app

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.session.SessionViewModel
import dev.trove.app.testing.COMPOSE_TIMEOUT_MS
import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.scrollAndClick
import dev.trove.app.testing.testHarness
import dev.trove.app.testing.waitForTag
import dev.trove.app.testing.waitForText
import dev.trove.core.auth.StoredCredential
import dev.trove.core.network.ItemCreateResponseDto
import dev.trove.core.network.ItemDto
import dev.trove.core.network.TroveApiException
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class AddFlowTest {
    @get:Rule
    val compose = createComposeRule()


    private fun harness(context: Context) = testHarness(
        context,
        tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel")),
        settingsStore = FakeSettingsStore("https://host.example"),
    )

    @Test
    fun submittingUrlShowsProcessingState() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = harness(context)
        harness.api.createResponse = ItemCreateResponseDto(
            item = ItemDto(
                id = "new-item",
                title = "新视频",
                processingState = "queued",
                hasAudio = true,
            ),
            deduplicated = false,
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-screen")
        compose.onNodeWithText("添加").performClick()
        waitForTag(compose, "add-url-input")
        compose.onNodeWithTag("add-url-input").performTextInput("https://youtu.be/abc")
        waitForTag(compose, "add-preview")
        compose.scrollAndClick("add-preview-submit")

        compose.waitUntil(COMPOSE_TIMEOUT_MS) { harness.api.createCalls.isNotEmpty() }
        waitForTag(compose, "add-processing")
        assertEquals("https://youtu.be/abc", harness.api.createCalls.single().url)
        compose.onNodeWithText("新视频").performScrollTo().assertIsDisplayed()
    }

    @Test
    fun unsupportedPlatformShowsHostError() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = harness(context)
        harness.api.createError = TroveApiException(
            code = "url.unsupported_platform",
            message = "Unsupported platform",
            statusCode = 422,
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-screen")
        compose.onNodeWithText("添加").performClick()
        waitForTag(compose, "add-url-input")
        compose.onNodeWithTag("add-url-input").performTextInput("https://example.com/video")
        waitForTag(compose, "add-preview")
        compose.scrollAndClick("add-preview-submit")

        waitForText(compose, "不支持这个平台。")
        compose.onNodeWithText("不支持这个平台。").performScrollTo().assertIsDisplayed()
    }

    @Test
    fun duplicateItemOpensExistingItem() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = harness(context)
        harness.api.createResponse = ItemCreateResponseDto(
            item = ItemDto(
                id = "existing",
                title = "已存在",
                processingState = "completed",
                hasAudio = true,
            ),
            deduplicated = true,
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-screen")
        compose.onNodeWithText("添加").performClick()
        waitForTag(compose, "add-url-input")
        compose.onNodeWithTag("add-url-input").performTextInput("https://youtu.be/abc")
        waitForTag(compose, "add-preview")
        compose.scrollAndClick("add-preview-submit")

        waitForTag(compose, "player-screen")
    }
}
