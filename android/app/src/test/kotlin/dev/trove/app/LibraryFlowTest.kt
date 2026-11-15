package dev.trove.app

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.core.app.ApplicationProvider
import dev.trove.app.session.SessionViewModel
import dev.trove.app.testing.FakeSettingsStore
import dev.trove.app.testing.FakeTokenStore
import dev.trove.app.testing.testHarness
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

private const val PLAYBACK_TIMEOUT_MS = 15_000L

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class LibraryFlowTest {
    @get:Rule
    val compose = createComposeRule()

    private fun waitForTag(tag: String) {
        compose.waitUntil(5_000) {
            compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
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

        waitForTag("library-item-item-1")
        compose.onNodeWithText("记忆是智能体的瓶颈").assertIsDisplayed()

        compose.onNodeWithTag("play-item-1").performScrollTo().performClick()
        compose.waitForIdle()
        compose.waitUntil(PLAYBACK_TIMEOUT_MS) { harness.player.requests.isNotEmpty() }
        assertEquals(
            "https://host.example/api/items/item-1/files/audio",
            harness.player.requests.single().url,
        )

        compose.onNodeWithTag("library-item-item-1").performScrollTo().performClick()
        waitForTag("player-screen")
    }


    @Test
    fun continueStripResumesInProgressItem() {
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

        waitForTag("continue-item-1")
        compose.onNodeWithTag("continue-item-1").performClick()
        compose.waitForIdle()
        compose.waitUntil(PLAYBACK_TIMEOUT_MS) { harness.player.requests.isNotEmpty() }
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

        waitForTag("library-item-item-1")
        compose.onNodeWithTag("play-item-1").performScrollTo().performClick()
        compose.waitForIdle()
        compose.waitUntil(PLAYBACK_TIMEOUT_MS) { harness.player.requests.isNotEmpty() }
        compose.onNodeWithTag("library-item-item-1").performScrollTo().performClick()
        waitForTag("player-screen")
        waitForTag("player-error")

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

        waitForTag("library-item-ready")
        compose.onNodeWithText("Ready item").assertIsDisplayed()

        compose.onNodeWithTag("filter-inbox").performScrollTo().performClick()

        compose.waitUntil(5_000) {
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

        compose.waitUntil(5_000) {
            compose.onAllNodesWithText("离线 · 显示已同步内容").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("已同步的 Item").assertIsDisplayed()
    }

    private suspend fun seedLocalItem(harness: dev.trove.app.testing.TestHarness) {
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
                downloadState = "none",
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
