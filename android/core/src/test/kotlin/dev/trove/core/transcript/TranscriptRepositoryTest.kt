package dev.trove.core.transcript

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import dev.trove.core.db.ArtifactEntity
import dev.trove.core.db.ItemEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.storage.ArtifactFileStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class TranscriptRepositoryTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    private lateinit var database: TroveDatabase
    private lateinit var fileStore: ArtifactFileStore
    private lateinit var repository: TranscriptRepository

    @Before
    fun setUp() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        database = TroveDatabase.inMemory(context)
        fileStore = ArtifactFileStore(temporaryFolder.newFolder("artifacts"))
        repository = TranscriptRepository(database, fileStore)
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun parsesGoldenTranscriptIntoRoom() = runBlocking {
        seedDownloadedTranscript()

        val result = repository.ensureParsed("item-1")

        assertEquals(TranscriptLoadResult.Ready(3), result)
        val segments = repository.observe("item-1").first()
        assertEquals(listOf(0, 1, 2), segments.map { it.seq })
        assertEquals(0, segments.first().startMs)
        assertEquals(4200, segments.first().endMs)
        assertTrue(segments.first().text.contains("智能体的瓶颈"))
        assertEquals(3, database.transcriptSegmentDao().countForItem("item-1"))
    }

    @Test
    fun reparsingReplacesOldSegments() = runBlocking {
        seedDownloadedTranscript()
        repository.ensureParsed("item-1")
        val file = checkNotNull(javaClass.getResource("/transcript.json")).readBytes()
        val artifact = database.artifactDao().find("item-1", "transcript")!!
        val target = fileStore.pathFor("item-1", "transcript", artifact.mime)
        target.writeBytes(file)

        repository.ensureParsed("item-1")

        assertEquals(3, database.transcriptSegmentDao().countForItem("item-1"))
    }

    @Test
    fun malformedTranscriptReportsFailureWithoutWritingRows() = runBlocking {
        seedDownloadedTranscript(contents = "{not-json")
        val result = repository.ensureParsed("item-1")
        assertEquals(TranscriptLoadResult.Failed, result)
        assertEquals(0, database.transcriptSegmentDao().countForItem("item-1"))
    }

    @Test
    fun missingDownloadIsReportedSeparately() = runBlocking {
        seedItem()
        database.artifactDao().upsert(
            ArtifactEntity(
                itemId = "item-1",
                kind = "transcript",
                sha256 = "a".repeat(64),
                size = 10,
                mime = "application/json",
                version = 1,
                localPath = null,
                downloadState = "none",
            )
        )
        assertEquals(TranscriptLoadResult.NotDownloaded, repository.ensureParsed("item-1"))
    }

    @Test
    fun parsesThousandSegmentTranscriptQuickly() {
        val segments = (0 until 1_000).joinToString(",") { index ->
            """{"seq":$index,"start_ms":${index * 1000},"end_ms":${index * 1000 + 900},"text":"seg $index"}"""
        }
        val document = """{"language":"zh","segments":[$segments]}"""
        val start = System.nanoTime()
        val parsed = TranscriptParser.parse(document)
        val elapsedMs = (System.nanoTime() - start) / 1_000_000
        assertEquals(1_000, parsed.size)
        assertEquals(999, parsed.last().seq)
        assertTrue("parse took ${elapsedMs}ms", elapsedMs < 2_000)
    }

    @Test
    fun timestampsUseTroveClockFormat() {
        assertEquals("0:00", TranscriptParser.timestamp(0))
        assertEquals("1:05", TranscriptParser.timestamp(65_000))
        assertEquals("1:02:05", TranscriptParser.timestamp(3_725_000))
    }

    @Test
    fun searchFiltersCaseInsensitivelyAndFindsRanges() {
        assertEquals(
            listOf(0 until 2, 2 until 4, 4 until 6, 6 until 8),
            highlightRanges("abABabAB", "ab"),
        )
        assertTrue(queryMatches("AI is useful", "ai"))
        assertTrue(queryMatches("记忆是瓶颈", "记忆"))
        assertTrue(queryMatches("anything", ""))
        assertTrue(highlightRanges("记忆是瓶颈", "记忆") == listOf(0 until 2))
    }

    private suspend fun seedItem() {
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
    }

    private suspend fun seedDownloadedTranscript(
        contents: String = checkNotNull(javaClass.getResource("/transcript.json")).readText(),
    ) {
        seedItem()
        val target = fileStore.pathFor("item-1", "transcript", "application/json")
        target.writeText(contents)
        database.artifactDao().upsert(
            ArtifactEntity(
                itemId = "item-1",
                kind = "transcript",
                sha256 = "a".repeat(64),
                size = contents.toByteArray().size.toLong(),
                mime = "application/json",
                version = 1,
                localPath = target.absolutePath,
                downloadState = "completed",
                downloadedBytes = target.length(),
            )
        )
    }
}
