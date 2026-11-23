package dev.trove.app

import android.content.Context
import androidx.compose.ui.test.assertContentDescriptionEquals
import androidx.compose.ui.test.assertCountEquals
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.session.SessionViewModel
import dev.trove.app.testing.COMPOSE_TIMEOUT_MS
import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.TestHarness
import dev.trove.app.testing.scrollAndClick
import dev.trove.app.testing.scrollAndClickText
import dev.trove.app.testing.testHarness
import dev.trove.app.testing.waitForTag
import dev.trove.core.auth.StoredCredential
import dev.trove.core.network.CollectionCreateResponseDto
import dev.trove.core.network.CollectionDto
import dev.trove.core.network.CollectionStatusDto
import dev.trove.core.network.LinkEpisodeDto
import dev.trove.core.network.LinkInspectResponseDto
import dev.trove.core.network.LinkWarningDto
import dev.trove.core.network.ManifestDto
import dev.trove.core.network.SyncFileDto
import dev.trove.core.network.SyncItemDto
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
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

        waitForTag(compose, "library-screen")
        compose.onNodeWithText("添加").performClick()
        waitForTag(compose, "add-url-input")
        compose.onNodeWithTag("add-url-input").performTextInput(url)
        waitForTag(compose, "add-preview")
        compose.scrollAndClick("add-preview-submit")
        waitForTag(compose, "add-collection-result")
        compose.onNodeWithText("合集已加入").performScrollTo().assertIsDisplayed()
        compose.scrollAndClickText("打开合集")
        waitForTag(compose, "collection-screen")
        compose.onNodeWithText("Fixture Collection").assertIsDisplayed()
        compose.onNodeWithText("Episode One").assertIsDisplayed()
        compose.onNodeWithText("Episode Two").assertIsDisplayed()
    }

    @Test
    fun collectionPreviewShowsUnknownDurationWhenUpstreamOmitsIt() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = harness(context)
        val url = "https://www.bilibili.com/video/BVtest"
        harness.api.inspectResponse = LinkInspectResponseDto(
            kind = "collection",
            rawUrl = url,
            canonicalUrl = url,
            title = "Fixture Collection",
            platform = "bilibili",
            episodeCount = 2,
            totalDurationSec = null,
            episodes = listOf(
                LinkEpisodeDto("Episode One", url, url, 1, null),
                LinkEpisodeDto("Episode Two", "$url?p=2", "$url?p=2", 2, null),
            ),
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-screen")
        compose.onNodeWithText("添加").performClick()
        waitForTag(compose, "add-url-input")
        compose.onNodeWithTag("add-url-input").performTextInput(url)
        waitForTag(compose, "add-preview")

        compose.onNodeWithText("时长未知", substring = true).performScrollTo().assertIsDisplayed()
    }

    @Test
    fun ignoredPlaylistWarningIsShownOnce() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = harness(context)
        val url = "https://www.youtube.com/watch?v=abc&list=PLtest"
        harness.api.inspectResponse = LinkInspectResponseDto(
            kind = "video",
            rawUrl = url,
            canonicalUrl = url,
            title = "Fixture Video",
            platform = "youtube",
            durationSec = 60.0,
            ignoredPlaylist = true,
            warnings = listOf(
                LinkWarningDto(
                    code = "link.ignored_playlist",
                    message = "链接里的播放列表参数已忽略，只添加当前视频。",
                )
            ),
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-screen")
        compose.onNodeWithText("添加").performClick()
        waitForTag(compose, "add-url-input")
        compose.onNodeWithTag("add-url-input").performTextInput(url)
        waitForTag(compose, "add-preview")

        compose.onAllNodesWithText("链接里的播放列表参数已忽略，只添加当前视频。")
            .assertCountEquals(1)
    }

    @Test
    fun collectionPlayButtonReflectsPlaybackAndStopsIt() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = harness(context)
        harness.api.manifestResponse = ManifestDto(
            items = listOf(
                syncItem("one", "Episode One", 1, ready = true),
                syncItem("two", "Episode Two", 2, ready = true),
            ),
            tombstones = emptyList(),
            nextCursor = "2",
            hasMore = false,
            epoch = "test-epoch",
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-collection-collection-1")
        compose.onNodeWithTag("library-collection-collection-1").performClick()
        waitForTag(compose, "collection-play-one")

        compose.onNodeWithTag("collection-play-one").performClick()
        waitForPlayerState(harness) { it.itemId == "one" && it.isPlaying }
        compose.onNodeWithTag("collection-play-one").assertContentDescriptionEquals("暂停")

        compose.onNodeWithTag("collection-play-one").performClick()
        waitForPlayerState(harness) { it.itemId == "one" && !it.isPlaying }
        compose.onNodeWithTag("collection-play-one").assertContentDescriptionEquals("播放")
    }

    @Test
    fun collectionEpisodeCoverShowsTitleInitialsInsteadOfIndex() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = harness(context)
        harness.api.manifestResponse = ManifestDto(
            items = listOf(
                syncItem("one", "Episode One", 1, ready = true),
                syncItem("two", "Episode Two", 2, ready = true),
            ),
            tombstones = emptyList(),
            nextCursor = "2",
            hasMore = false,
            epoch = "test-epoch",
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-collection-collection-1")
        compose.onNodeWithTag("library-collection-collection-1").performClick()
        waitForTag(compose, "collection-screen")

        compose.onNodeWithTag("collection-episodes").performScrollToIndex(1)
        compose.onAllNodesWithText("01").assertCountEquals(1)
        compose.onNodeWithText("EO").assertIsDisplayed()

        compose.onNodeWithTag("collection-episodes").performScrollToIndex(2)
        compose.onAllNodesWithText("02").assertCountEquals(1)
        compose.onNodeWithText("ET").assertIsDisplayed()
    }

    @Test
    fun collectionDownloadAllQueuesEveryEpisodeAndShowsDownloadStates() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = harness(context)
        harness.api.manifestResponse = ManifestDto(
            items = listOf(
                syncItem("one", "Episode One", 1, ready = true),
                syncItem("two", "Episode Two", 2, ready = true),
            ),
            tombstones = emptyList(),
            nextCursor = "2",
            hasMore = false,
            epoch = "test-epoch",
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-collection-collection-1")
        compose.onNodeWithTag("library-collection-collection-1").performClick()
        waitForTag(compose, "collection-screen")
        compose.onNodeWithText("已下载 0/2").assertIsDisplayed()
        compose.onNodeWithTag("collection-episodes").performScrollToIndex(1)
        compose.onNodeWithTag("collection-episode-one").assertTextContains("未下载")
        compose.onNodeWithTag("collection-episodes").performScrollToIndex(2)
        compose.onNodeWithTag("collection-episode-two").assertTextContains("未下载")

        compose.onNodeWithTag("collection-episodes").performScrollToIndex(0)
        compose.onNodeWithTag("collection-download-all").performClick()
        compose.waitUntil(COMPOSE_TIMEOUT_MS) {
            compose.waitForIdle()
            runBlocking {
                val states = harness.container.database.artifactDao().forItem("one")
                    .plus(harness.container.database.artifactDao().forItem("two"))
                    .map { it.downloadState }
                states.size == 2 && states.all { it == "queued" }
            }
        }

        val states = runBlocking {
            harness.container.database.artifactDao().forItem("one")
                .plus(harness.container.database.artifactDao().forItem("two"))
                .map { it.downloadState }
        }
        assertTrue("states=$states", states.all { it == "queued" })
        compose.onNodeWithTag("collection-episodes").performScrollToIndex(0)
        compose.onNodeWithTag("collection-download-all").assertTextContains("等待下载 0/2")
        compose.onNodeWithTag("collection-episodes").performScrollToIndex(1)
        compose.onNodeWithTag("collection-episode-one").assertTextContains("等待下载")
        compose.onNodeWithTag("collection-episodes").performScrollToIndex(2)
        compose.onNodeWithTag("collection-episode-two").assertTextContains("等待下载")
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

        waitForTag(compose, "library-collection-collection-1")
        compose.onNodeWithTag("library-collection-collection-1").performClick()
        waitForTag(compose, "collection-screen")
        compose.onNodeWithContentDescription("更多").performClick()
        compose.onNodeWithText("删除合集").performClick()
        waitForTag(compose, "collection-delete-option-ungroup")
        compose.onNodeWithTag("collection-delete-option-ungroup").performClick()
        compose.waitUntil(COMPOSE_TIMEOUT_MS) {
            harness.api.deletedCollections.contains("collection-1" to "ungroup")
        }
    }

    private fun waitForPlayerState(
        harness: TestHarness,
        predicate: (dev.trove.playback.PlaybackState) -> Boolean,
    ) {
        compose.waitUntil(COMPOSE_TIMEOUT_MS) {
            compose.waitForIdle()
            predicate(harness.player.state.value)
        }
    }

    private fun syncItem(
        id: String,
        title: String,
        index: Int,
        ready: Boolean = false,
    ) = SyncItemDto(
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
        durationSec = 60.0,
        processingState = if (ready) "completed" else "queued",
        hasAudio = ready,
        hasBook = false,
        files = if (ready) {
            listOf(
                SyncFileDto(
                    kind = "audio",
                    sha256 = "a".repeat(64),
                    size = 100,
                    mime = "audio/mp4",
                    version = 1,
                    url = "/api/items/$id/files/audio",
                )
            )
        } else {
            emptyList()
        },
    )
}
