package dev.trove.app

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.session.SessionViewModel
import dev.trove.app.testing.COMPOSE_TIMEOUT_MS
import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.TestHarness
import dev.trove.app.testing.testHarness
import dev.trove.app.testing.waitForTag
import dev.trove.app.testing.waitForText
import dev.trove.core.auth.StoredCredential
import dev.trove.core.db.ArtifactEntity
import dev.trove.core.db.ItemEntity
import dev.trove.core.network.ManifestDto
import dev.trove.core.network.SyncFileDto
import dev.trove.core.network.SyncItemDto
import dev.trove.core.network.TroveNetworkException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class LibraryFlowTest {
    @get:Rule
    val compose = createComposeRule()

    private fun waitForPlaybackRequest(harness: TestHarness) {
        // waitUntil only drives the Compose clock; pump the main looper so the
        // Room-backed ViewModel coroutine can resume and call the player.
        compose.waitUntil(COMPOSE_TIMEOUT_MS) {
            compose.waitForIdle()
            harness.player.requests.isNotEmpty()
        }
    }

    private fun signedInHarness(context: Context) = testHarness(
        context,
        tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel")),
        settingsStore = FakeSettingsStore("https://host.example"),
    )

    @Test
    fun libraryShowsSyncedItemsAndPlayOpensPlayer() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = signedInHarness(context)
        harness.api.manifestResponse = ManifestDto(
            items = listOf(syncItem("item-1", "记忆是智能体的瓶颈", "completed")),
            tombstones = emptyList(),
            nextCursor = "1",
            hasMore = false,
            epoch = "epoch",
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-item-item-1")
        compose.onNodeWithText("记忆是智能体的瓶颈").assertIsDisplayed()

        compose.onNodeWithTag("play-item-1").performScrollTo().performClick()
        compose.waitForIdle()
        waitForPlaybackRequest(harness)
        assertEquals(
            "https://host.example/api/items/item-1/files/audio",
            harness.player.requests.single().url,
        )

        compose.onNodeWithTag("library-item-item-1").performScrollTo().performClick()
        waitForTag(compose, "player-screen")
    }


    @Test
    fun inProgressItemQuickPlayResumes() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = signedInHarness(context)
        harness.api.manifestResponse = ManifestDto(
            items = listOf(
                syncItem("item-1", "进行中的内容", "completed"),
                syncItem("item-2", "已完成的内容", "completed"),
            ),
            tombstones = emptyList(),
            nextCursor = "2",
            hasMore = false,
            epoch = "epoch",
        )
        harness.api.stateResponse = dev.trove.core.network.SyncStateDto(
            items = listOf(
                dev.trove.core.network.SyncStateItemDto(
                    id = "item-1",
                    stateSeq = 2,
                    audioPositionSec = 20.0,
                    consumptionState = "in_progress",
                    lastConsumedAt = 2,
                ),
                dev.trove.core.network.SyncStateItemDto(
                    id = "item-2",
                    stateSeq = 3,
                    audioPositionSec = 100.0,
                    consumptionState = "finished",
                    lastConsumedAt = 1,
                ),
            ),
            nextCursor = "3",
            hasMore = false,
            epoch = "epoch",
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-item-item-1")
        compose.onNodeWithTag("play-item-1").performScrollTo().performClick()
        compose.waitForIdle()
        waitForPlaybackRequest(harness)
        assertEquals(
            "https://host.example/api/items/item-1/files/audio",
            harness.player.requests.single().url,
        )
    }

    @Test
    fun playbackErrorShowsReadableMessage() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = signedInHarness(context)
        harness.player.errorOnPlay = "ERROR_CODE_IO_NETWORK_CONNECTION_FAILED"
        harness.api.manifestResponse = ManifestDto(
            items = listOf(syncItem("item-1", "记忆是智能体的瓶颈", "completed")),
            tombstones = emptyList(),
            nextCursor = "1",
            hasMore = false,
            epoch = "epoch",
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-item-item-1")
        compose.onNodeWithTag("play-item-1").performScrollTo().performClick()
        compose.waitForIdle()
        waitForPlaybackRequest(harness)
        compose.onNodeWithTag("library-item-item-1").performScrollTo().performClick()
        waitForTag(compose, "player-screen")
        waitForTag(compose, "player-error")

        compose.onNodeWithText("网络连接失败，无法播放。请检查网络后重试。").assertIsDisplayed()
    }

    @Test
    fun inboxFilterHidesReadyItems() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = signedInHarness(context)
        harness.api.manifestResponse = ManifestDto(
            items = listOf(
                syncItem("ready", "Ready item", "completed"),
                syncItem("failed", "Failed item", "failed"),
            ),
            tombstones = emptyList(),
            nextCursor = "2",
            hasMore = false,
            epoch = "epoch",
        )
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-item-ready")
        waitForTag(compose, "library-item-failed")
        compose.onNodeWithText("Ready item").assertIsDisplayed()

        compose.onNodeWithTag("filter-inbox").performScrollTo().performClick()

        compose.waitUntil(COMPOSE_TIMEOUT_MS) {
            compose.waitForIdle()
            compose.onAllNodesWithText("Ready item").fetchSemanticsNodes().isEmpty()
        }
        compose.onNodeWithText("Failed item").assertIsDisplayed()
        compose.onNodeWithText("处理失败").assertIsDisplayed()
    }

    @Test
    fun offlineStatusKeepsSyncedLibraryVisible() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = signedInHarness(context)
        harness.api.manifestError = TroveNetworkException("offline")
        runBlocking { seedLocalItem(harness) }
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForText(compose, "离线 · 显示已同步内容")
        compose.onNodeWithText("已同步的 Item").assertIsDisplayed()
    }

    @Test
    fun queuedDownloadsAreReportedAndResumed() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = signedInHarness(context)
        harness.api.manifestResponse = ManifestDto(
            items = listOf(syncItem("offline-1", "已同步的 Item", "completed")),
            tombstones = emptyList(),
            nextCursor = "1",
            hasMore = false,
            epoch = "epoch",
        )
        harness.api.stateResponse = dev.trove.core.network.SyncStateDto(
            items = emptyList(),
            nextCursor = "1",
            hasMore = false,
            epoch = "epoch",
        )
        runBlocking { seedLocalItem(harness, downloadState = "queued") }
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        compose.waitUntil(COMPOSE_TIMEOUT_MS) {
            compose.waitForIdle()
            harness.downloadQueue.enqueued.contains("offline-1")
        }
        waitForText(compose, "已同步 · 1 项等待下载")
    }

    private suspend fun seedLocalItem(
        harness: dev.trove.app.testing.TestHarness,
        downloadState: String = "none",
    ) {
        val database = harness.container.database
        database.itemDao().upsert(
            ItemEntity(
                id = "offline-1",
                version = 1,
                sourceType = "video_url",
                platform = "youtube",
                title = "已同步的 Item",
                author = null,
                publishedAt = null,
                fetchedAt = 1,
                language = "zh",
                durationSec = 100.0,
                summary = null,
                processingState = "completed",
                errorCode = null,
                errorMessage = null,
                hasAudio = true,
                hasBook = false,
                consumptionState = "unstarted",
                audioPositionSec = 0.0,
                bookLocator = null,
                lastConsumedAt = null,
                contentSeq = 1,
                stateSeq = 1,
                lastSyncedAt = 1,
            )
        )
        database.artifactDao().upsert(
            ArtifactEntity(
                itemId = "offline-1",
                kind = "audio",
                sha256 = "a".repeat(64),
                size = 100,
                mime = "audio/mp4",
                version = 1,
                localPath = null,
                downloadState = downloadState,
            )
        )
    }

    private fun syncItem(id: String, title: String, processingState: String) = SyncItemDto(
        id = id,
        version = 1,
        sourceType = "video_url",
        platform = "youtube",
        title = title,
        author = "作者",
        publishedAt = "2026-10-01",
        fetchedAt = 1_790_000_000_000,
        language = "zh",
        durationSec = 100.0,
        summary = "Summary",
        tags = listOf("AI"),
        processingState = processingState,
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
