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
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.session.SessionViewModel
import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.testHarness
import dev.trove.core.auth.StoredCredential
import dev.trove.core.network.CollectionCreateResponseDto
import dev.trove.core.network.CollectionDto
import dev.trove.core.network.CollectionStatusDto
import dev.trove.core.network.LinkEpisodeDto
import dev.trove.core.network.LinkInspectResponseDto
import dev.trove.core.network.ManifestDto
import dev.trove.core.network.SyncItemDto
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class CollectionFlowTest {
    @get:Rule
    val compose = createComposeRule()

    private fun harness(context: Context) = testHarness(
        context,
        tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel")),
        settingsStore = FakeSettingsStore("https://host.example"),
    )

    @Test
    fun addingCollectionShowsResultAndOpensCollection() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = harness(context)
        val url = "https://www.youtube.com/playlist?list=PLtest"
        harness.api.inspectResponse = LinkInspectResponseDto(
            kind = "collection",
            rawUrl = url,
            canonicalUrl = url,
            title = "Fixture Collection",
            author = "Fixture Channel",
            platform = "youtube",
            episodeCount = 2,
            totalDurationSec = 120.0,
            episodes = listOf(
                LinkEpisodeDto("Episode One", "https://youtu.be/one", "https://youtu.be/one", 1, 60.0),
                LinkEpisodeDto("Episode Two", "https://youtu.be/two", "https://youtu.be/two", 2, 60.0),
            ),
        )
        harness.api.collectionCreateResponse = CollectionCreateResponseDto(
            collection = CollectionDto(
                id = "collection-1",
                sourceKey = url,
                platform = "youtube",
                title = "Fixture Collection",
                episodeCount = 2,
                status = CollectionStatusDto(queued = 2, total = 2),
            ),
            addedCount = 2,
            runCount = 2,
        )
        harness.api.manifestResponse = ManifestDto(
            items = listOf(
                syncItem("one", "Episode One", 1),
                syncItem("two", "Episode Two", 2),
            ),
            tombstones = emptyList(),
            nextCursor = "2",
            hasMore = false,
            epoch = "test-epoch",
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag("library-screen")
        compose.onNodeWithText("添加").performClick()
        waitForTag("add-url-input")
        compose.onNodeWithTag("add-url-input").performTextInput(url)
        waitForTag("add-preview")
        compose.onNodeWithTag("add-preview-submit").performScrollTo().performClick()
        waitForTag("add-collection-result")
        compose.onNodeWithText("合集已加入").performScrollTo().assertIsDisplayed()
        compose.onNodeWithText("打开合集").performScrollTo().performClick()
        waitForTag("collection-screen")
        compose.onNodeWithText("Fixture Collection").assertIsDisplayed()
        compose.onNodeWithText("Episode One").assertIsDisplayed()
        compose.onNodeWithText("Episode Two").assertIsDisplayed()
    }

    @Test
    fun libraryShowsCollectionCardAndDeletesWithUngroup() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = harness(context)
        harness.api.manifestResponse = ManifestDto(
            items = listOf(
                syncItem("one", "Episode One", 1),
                syncItem("two", "Episode Two", 2),
            ),
            tombstones = emptyList(),
            nextCursor = "2",
            hasMore = false,
            epoch = "test-epoch",
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag("library-collection-collection-1")
        compose.onNodeWithTag("library-collection-collection-1").performClick()
        waitForTag("collection-screen")
        compose.onNodeWithContentDescription("更多").performClick()
        compose.onNodeWithText("删除合集").performClick()
        waitForTag("collection-delete-option-ungroup")
        compose.onNodeWithTag("collection-delete-option-ungroup").performClick()
        compose.waitUntil(5_000) {
            harness.api.deletedCollections.contains("collection-1" to "ungroup")
        }
    }

    private fun syncItem(id: String, title: String, index: Int) = SyncItemDto(
        id = id,
        version = 1,
        sourceType = "video_url",
        platform = "youtube",
        collectionId = "collection-1",
        collectionIndex = index,
        collectionTitle = "Fixture Collection",
        collectionPlatform = "youtube",
        collectionSourceUrl = "https://www.youtube.com/playlist?list=PLtest",
        title = title,
        fetchedAt = 1_000L + index,
        processingState = "queued",
        hasAudio = false,
        hasBook = false,
    )

    private fun waitForTag(tag: String) {
        compose.waitUntil(8_000) {
            compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
        }
    }
}
