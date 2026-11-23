package dev.trove.core.download

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import dev.trove.core.db.ArtifactEntity
import dev.trove.core.db.ItemEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.network.TroveHttpClients
import dev.trove.core.storage.ArtifactFileStore
import dev.trove.core.sync.DownloadQueue
import java.security.MessageDigest
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okio.Buffer
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class ArtifactDownloaderTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    private lateinit var database: TroveDatabase
    private lateinit var fileStore: ArtifactFileStore
    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        database = TroveDatabase.inMemory(context)
        fileStore = ArtifactFileStore(temporaryFolder.newFolder("artifacts"))
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.close()
        database.close()
    }

    private fun downloader(
        quotaBytes: Long = DEFAULT_QUOTA_BYTES,
        host: String = server.url("/").toString(),
        nowPlaying: () -> String? = { null },
    ) = ArtifactDownloader(
        database = database,
        fileStore = fileStore,
        hostProvider = { host },
        tokenProvider = { "secret-token" },
        preferencesProvider = { DownloadPreferences(quotaBytes = quotaBytes) },
        clientFactory = { TroveHttpClients.create(it, 60) },
        nowPlayingItemId = nowPlaying,
    )

    @Test
    fun downloadsArtifactWithBearerAndVerifiesSha() = runBlocking {
        val bytes = fixtureBytes()
        seedItem(bytes, kind = "transcript")
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .addHeader("ETag", "\"${sha256(bytes)}\"")
                .body(Buffer().write(bytes))
                .build()
        )

        val completed = downloader().downloadItem("item-1")

        assertEquals(1, completed)
        val artifact = database.artifactDao().find("item-1", "transcript")!!
        assertEquals("completed", artifact.downloadState)
        assertEquals(sha256(bytes), artifact.sha256)
        val file = fileStore.existingFile("item-1", "transcript", artifact.localPath)
        assertTrue(file!!.isFile)
        assertArrayEquals(bytes, file.readBytes())
        assertEquals("\"${sha256(bytes)}\"", artifact.etag)
        val request = server.takeRequest()
        assertEquals("/api/items/item-1/files/transcript", request.url.encodedPath)
        assertEquals("Bearer secret-token", request.headers["Authorization"])
    }

    @Test
    fun resumesPartialFileWithRangeAndIfRange() = runBlocking {
        val bytes = fixtureBytes()
        seedItem(bytes, kind = "transcript")
        val target = fileStore.pathFor("item-1", "transcript", "application/json")
        val part = fileStore.partFor(target)
        part.writeBytes(bytes.copyOfRange(0, 200))
        database.artifactDao().upsert(
            database.artifactDao().find("item-1", "transcript")!!.copy(
                etag = "\"v1\"",
                downloadState = "failed",
                downloadedBytes = 200,
            )
        )
        server.enqueue(
            MockResponse.Builder()
                .code(206)
                .addHeader("ETag", "\"v1\"")
                .body(Buffer().write(bytes.copyOfRange(200, bytes.size)))
                .build()
        )

        downloader().downloadItem("item-1")

        val request = server.takeRequest()
        assertEquals("bytes=200-", request.headers["Range"])
        assertEquals("\"v1\"", request.headers["If-Range"])
        assertArrayEquals(bytes, target.readBytes())
        assertFalse(part.exists())
        assertEquals("completed", database.artifactDao().find("item-1", "transcript")?.downloadState)
    }

    @Test
    fun changedEtagDiscardsPartialFileAndDownloadsFromScratch() = runBlocking {
        val bytes = fixtureBytes()
        seedItem(bytes, kind = "transcript")
        val target = fileStore.pathFor("item-1", "transcript", "application/json")
        val part = fileStore.partFor(target)
        part.writeText("stale partial content")
        database.artifactDao().upsert(
            database.artifactDao().find("item-1", "transcript")!!.copy(
                etag = "\"v1\"",
                downloadState = "failed",
                downloadedBytes = part.length(),
            )
        )
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .addHeader("ETag", "\"v2\"")
                .body(Buffer().write(bytes))
                .build()
        )

        downloader().downloadItem("item-1")

        assertEquals("\"v1\"", server.takeRequest().headers["If-Range"])
        assertArrayEquals(bytes, target.readBytes())
        assertEquals("\"v2\"", database.artifactDao().find("item-1", "transcript")?.etag)
    }

    @Test
    fun checksumMismatchFailsAndDeletesPartialFile() = runBlocking {
        val bytes = fixtureBytes()
        seedItem(bytes, kind = "transcript", sha = "f".repeat(64))
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .body(Buffer().write(bytes))
                .build()
        )

        try {
            downloader().downloadItem("item-1")
            fail("expected checksum failure")
        } catch (error: DownloadException) {
            assertEquals(SHA_MISMATCH, error.code)
            assertTrue(error.retriable)
        }

        val target = fileStore.pathFor("item-1", "transcript", "application/json")
        assertFalse(target.exists())
        assertFalse(fileStore.partFor(target).exists())
        assertEquals("failed", database.artifactDao().find("item-1", "transcript")?.downloadState)
    }

    @Test
    fun unauthorizedDownloadNotifiesSession() = runBlocking {
        seedItem(fixtureBytes(), kind = "transcript")
        server.enqueue(MockResponse.Builder().code(401).build())
        var unauthorizedCode: String? = null
        val downloader = ArtifactDownloader(
            database = database,
            fileStore = fileStore,
            hostProvider = { server.url("/").toString() },
            tokenProvider = { "revoked" },
            clientFactory = { TroveHttpClients.create(it, 60) },
            onUnauthorized = { unauthorizedCode = it },
        )

        try {
            downloader.downloadItem("item-1")
            fail("expected HTTP failure")
        } catch (error: DownloadException) {
            assertEquals(HTTP_ERROR, error.code)
        }
        assertEquals("auth.device_token_invalid", unauthorizedCode)
    }

    @Test
    fun quotaExceededBlocksBeforeNetwork() = runBlocking {
        seedItem(fixtureBytes(), kind = "transcript")
        try {
            downloader(quotaBytes = 10).downloadItem("item-1")
            fail("expected quota failure")
        } catch (error: DownloadException) {
            assertEquals(QUOTA_EXCEEDED, error.code)
            assertFalse(error.retriable)
        }
        assertEquals(0, server.requestCount)
    }

    @Test
    fun removeDownloadOnlyClearsLocalState() = runBlocking {
        val bytes = fixtureBytes()
        seedItem(bytes, kind = "transcript")
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .body(Buffer().write(bytes))
                .build()
        )
        val downloader = downloader()
        downloader.downloadItem("item-1")
        database.transcriptSegmentDao().insertAll(
            listOf(
                dev.trove.core.db.TranscriptSegmentEntity(
                    itemId = "item-1",
                    seq = 0,
                    startMs = 0,
                    endMs = 10,
                    text = "cached",
                )
            )
        )
        val artifact = database.artifactDao().find("item-1", "transcript")!!
        val file = fileStore.existingFile("item-1", "transcript", artifact.localPath)!!

        downloader.removeDownload("item-1")

        assertFalse(file.exists())
        val cleared = database.artifactDao().find("item-1", "transcript")!!
        assertEquals("none", cleared.downloadState)
        assertNull(cleared.localPath)
        assertEquals(0, cleared.downloadedBytes)
        assertEquals(0, database.transcriptSegmentDao().countForItem("item-1"))
        assertEquals(1, server.requestCount)
    }

    @Test
    fun removingDownloadOfPlayingItemDefersAudioFileDeletion() = runBlocking {
        val bytes = fixtureBytes()
        seedItem(bytes, kind = "audio")
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .body(Buffer().write(bytes))
                .build()
        )
        val downloader = downloader(nowPlaying = { "item-1" })
        downloader.downloadItem("item-1")
        val artifact = database.artifactDao().find("item-1", "audio")!!
        val file = fileStore.existingFile("item-1", "audio", artifact.localPath)!!

        downloader.removeDownload("item-1")

        assertTrue(file.exists())
        assertEquals(1, database.pendingDeletionDao().all().size)
        assertEquals("none", database.artifactDao().find("item-1", "audio")?.downloadState)
    }

    @Test
    fun redownloadClearsDeferredDeletionForTheSamePath() = runBlocking {
        val bytes = fixtureBytes()
        seedItem(bytes, kind = "audio")
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .body(Buffer().write(bytes))
                .build()
        )
        val downloader = downloader(nowPlaying = { "item-1" })
        downloader.downloadItem("item-1")
        val artifact = database.artifactDao().find("item-1", "audio")!!
        val file = fileStore.existingFile("item-1", "audio", artifact.localPath)!!
        downloader.removeDownload("item-1")
        assertEquals(1, database.pendingDeletionDao().all().size)

        val manager = DefaultDownloadManager(database, downloader, FakeQueue())
        manager.enqueue("item-1")
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .body(Buffer().write(bytes))
                .build()
        )
        downloader.downloadItem("item-1")

        assertEquals(0, database.pendingDeletionDao().all().size)
        assertEquals("completed", database.artifactDao().find("item-1", "audio")?.downloadState)
        assertTrue(file.exists())
    }

    @Test
    fun managerQueuesPausesAndRemovesItem() = runBlocking {
        seedItem(fixtureBytes(), kind = "transcript")
        val queue = FakeQueue()
        val manager = DefaultDownloadManager(database, downloader(), queue)

        manager.enqueue("item-1")
        assertEquals(listOf("item-1"), queue.enqueued)
        assertEquals("queued", database.artifactDao().find("item-1", "transcript")?.downloadState)

        manager.pause("item-1")
        assertEquals("paused", database.artifactDao().find("item-1", "transcript")?.downloadState)

        manager.remove("item-1")
        assertEquals("none", database.artifactDao().find("item-1", "transcript")?.downloadState)
    }

    @Test
    fun managerResumesQueuedDownloadWhenNoDownloadIsActive() = runBlocking {
        seedItem(fixtureBytes(), kind = "transcript")
        val queue = FakeQueue()
        val manager = DefaultDownloadManager(database, downloader(), queue)

        manager.resumePending()
        assertEquals(listOf("item-1"), queue.enqueued)

        database.artifactDao().setDownloadState("item-1", "transcript", "downloading", null)
        queue.enqueued.clear()
        manager.resumePending()
        assertTrue(queue.enqueued.isEmpty())

        database.artifactDao().setDownloadState("item-1", "transcript", "none", null)
        manager.resumePending()
        assertTrue(queue.enqueued.isEmpty())
    }

    @Test
    fun managerQueuesWholeCollectionWithOneRequest() = runBlocking {
        seedItem(fixtureBytes(), kind = "transcript")
        val queue = FakeQueue()
        val manager = DefaultDownloadManager(database, downloader(), queue)

        manager.enqueueAll(listOf("item-1", "missing-item"))

        assertEquals(listOf("item-1"), queue.enqueued)
        assertEquals("queued", database.artifactDao().find("item-1", "transcript")?.downloadState)

        database.artifactDao().setDownloadState("item-1", "transcript", "completed", null)
        queue.enqueued.clear()
        manager.enqueueAll(listOf("item-1"))
        assertTrue(queue.enqueued.isEmpty())
    }

    private suspend fun seedItem(
        bytes: ByteArray,
        kind: String,
        sha: String = sha256(bytes),
    ) {
        database.itemDao().upsert(
            ItemEntity(
                id = "item-1",
                version = 1,
                sourceType = "video_url",
                platform = "youtube",
                title = "Item",
                author = null,
                publishedAt = null,
                fetchedAt = 1,
                language = "zh",
                durationSec = 100.0,
                summary = null,
                processingState = "completed",
                errorCode = null,
                errorMessage = null,
                hasAudio = kind == "audio",
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
                kind = kind,
                sha256 = sha,
                size = bytes.size.toLong(),
                mime = if (kind == "transcript") "application/json" else "audio/mp4",
                version = 1,
                localPath = null,
                downloadState = "queued",
            )
        )
    }

    private fun fixtureBytes(): ByteArray =
        checkNotNull(javaClass.getResource("/transcript.json")).readBytes()

    private fun sha256(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes)
            .joinToString("") { "%02x".format(it) }

    private class FakeQueue : DownloadQueue {
        val enqueued = mutableListOf<String>()

        override suspend fun enqueue(itemId: String) {
            enqueued += itemId
        }
    }
}
