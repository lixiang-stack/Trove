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
import androidx.compose.ui.test.performTextInput
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
import dev.trove.core.network.TranscriptResponseDto
import dev.trove.core.network.TranscriptSegmentDto
import dev.trove.core.network.TroveNetworkException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class TranscriptFlowTest {
    @get:Rule
    val compose = createComposeRule()

    @Test
    fun transcriptRendersAndSearchesOfflineCopy() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = testHarness(
            context,
            tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel")),
            settingsStore = FakeSettingsStore("https://host.example"),
        )
        harness.api.manifestError = TroveNetworkException("offline")
        runBlocking { seedTranscriptItem(harness) }
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-item-item-1")
        compose.onNodeWithTag("library-item-item-1").performScrollTo().performClick()
        waitForTag(compose, "player-screen")
        waitForTag(compose, "player-transcript-open")

        compose.onNodeWithTag("player-transcript-open").performScrollTo().performClick()
        waitForTag(compose, "player-transcript-full")
        compose.onNodeWithTag("player-transcript-full").performScrollTo().performClick()
        waitForTag(compose, "transcript-screen")
        waitForTag(compose, "transcript-segment-0")
        compose.onNodeWithText("3 段").assertIsDisplayed()

        compose.onNodeWithTag("transcript-search").performTextInput("上下文")

        compose.waitUntil(COMPOSE_TIMEOUT_MS) {
            compose.waitForIdle()
            compose.onAllNodesWithTag("transcript-segment-0").fetchSemanticsNodes().isEmpty()
        }
        compose.onNodeWithTag("transcript-segment-1").assertIsDisplayed()
        compose.onNodeWithText("1 个匹配").assertIsDisplayed()

        assertTrue(
            compose.onAllNodesWithText("今天想聊一个我最近反复想到的问题：为什么智能体的瓶颈不是模型，而是记忆。")
                .fetchSemanticsNodes()
                .isEmpty()
        )
    }

    @Test
    fun transcriptLoadsOnlineWithoutDownloadingItem() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = testHarness(
            context,
            tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel")),
            settingsStore = FakeSettingsStore("https://host.example"),
        )
        harness.api.manifestError = TroveNetworkException("offline")
        harness.api.transcriptResponse = TranscriptResponseDto(
            itemId = "item-1",
            segments = listOf(
                TranscriptSegmentDto(0, 0, 4_200, "在线 transcript"),
                TranscriptSegmentDto(1, 4_200, 8_000, "第二段"),
            ),
        )
        runBlocking { seedTranscriptItem(harness, downloaded = false) }
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-item-item-1")
        compose.onNodeWithTag("library-item-item-1").performScrollTo().performClick()
        waitForTag(compose, "player-screen")

        waitForText(compose, "在线 transcript")
        assertTrue(harness.api.transcriptRequests.contains("item-1"))
        compose.onNodeWithTag("player-transcript-open").performScrollTo().performClick()
        waitForTag(compose, "player-transcript-full")
        assertTrue(compose.onAllNodesWithText("第二段").fetchSemanticsNodes().isNotEmpty())
    }

    @Test
    fun transcriptNotDownloadedShowsPrompt() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val harness = testHarness(
            context,
            tokenStore = FakeTokenStore(StoredCredential("token", "device-1", "Pixel")),
            settingsStore = FakeSettingsStore("https://host.example"),
        )
        harness.api.manifestError = TroveNetworkException("offline")
        runBlocking { seedTranscriptItem(harness, downloaded = false) }
        val viewModel = SessionViewModel(harness.container.sessionController)
        compose.setContent { TroveApp(viewModel, harness.container) }

        waitForTag(compose, "library-item-item-1")
        compose.onNodeWithTag("library-item-item-1").performScrollTo().performClick()
        waitForTag(compose, "player-screen")

        compose.onNodeWithText("Transcript 暂不可用")
            .performScrollTo()
            .assertIsDisplayed()
        compose.onNodeWithText("联网后自动加载；下载 Item 可离线阅读。")
            .performScrollTo()
            .assertIsDisplayed()
    }

    private suspend fun seedTranscriptItem(
        harness: TestHarness,
        downloaded: Boolean = true,
    ) {
        val database = harness.container.database
        val fileStore = harness.container.fileStore
        val transcriptBytes = checkNotNull(javaClass.getResource("/transcript.json")).readBytes()
        val transcriptFile = fileStore.pathFor("item-1", "transcript", "application/json")
        if (downloaded) transcriptFile.writeBytes(transcriptBytes)
        database.itemDao().upsert(
            ItemEntity(
                id = "item-1",
                version = 1,
                sourceType = "video_url",
                platform = "youtube",
                title = "记忆是智能体的瓶颈",
                author = "作者",
                publishedAt = null,
                fetchedAt = 1,
                language = "zh",
                durationSec = 100.0,
                summary = "Summary",
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
                itemId = "item-1",
                kind = "audio",
                sha256 = "a".repeat(64),
                size = 100,
                mime = "audio/mp4",
                version = 1,
                localPath = null,
                downloadState = "none",
            )
        )
        database.artifactDao().upsert(
            ArtifactEntity(
                itemId = "item-1",
                kind = "transcript",
                sha256 = "b".repeat(64),
                size = transcriptBytes.size.toLong(),
                mime = "application/json",
                version = 1,
                localPath = if (downloaded) transcriptFile.absolutePath else null,
                downloadState = if (downloaded) "completed" else "none",
                downloadedBytes = if (downloaded) transcriptBytes.size.toLong() else 0,
            )
        )
    }
}
