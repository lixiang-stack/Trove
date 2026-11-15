package dev.trove.app

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.session.SessionViewModel
import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.testHarness
import dev.trove.core.auth.StoredCredential
import dev.trove.core.network.ManifestDto
import dev.trove.core.network.SyncFileDto
import dev.trove.core.network.SyncItemDto
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class SearchFlowTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    fun metadataSearchFiltersLibraryItems() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = testHarness(
            context,
            tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel")),
            settingsStore = FakeSettingsStore("https://host.example"),
        )
        harness.api.manifestResponse = ManifestDto(
            items = listOf(
                item("a", "Alpha 2025"),
                item("b", "Beta"),
            ),
            tombstones = emptyList(),
            nextCursor = "2",
            hasMore = false,
            epoch = "epoch",
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag("library-item-a")
        compose.onNodeWithText("搜索").performClick()
        waitForTag("search-screen")
        compose.onNodeWithTag("search-input").performTextInput("2025")

        compose.waitUntil(5_000) {
            compose.onAllNodesWithText("Alpha 2025").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("Alpha 2025").assertIsDisplayed()
        assertTrue(compose.onAllNodesWithText("Beta").fetchSemanticsNodes().isEmpty())
    }

    private fun waitForTag(tag: String) {
        compose.waitUntil(5_000) {
            compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
        }
    }

    private fun item(id: String, title: String) = SyncItemDto(
        id = id,
        version = 1,
        sourceType = "video_url",
        platform = "youtube",
        title = title,
        author = "作者",
        fetchedAt = 1_790_000_000_000,
        language = "zh",
        durationSec = 100.0,
        summary = "summary",
        tags = listOf("AI"),
        processingState = "completed",
        hasAudio = true,
        hasBook = false,
        files = listOf(
            SyncFileDto(
                kind = "audio",
                sha256 = "a".repeat(64),
                size = 100,
                mime = "audio/mp4",
                version = 1,
                url = "/api/items/$id/files/audio",
            )
        ),
    )
}
