package dev.trove.core.network

import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DtoContractTest {
    private val json = Json { ignoreUnknownKeys = true }

    private fun resource(name: String): String =
        checkNotNull(javaClass.getResource("/$name")) { "missing fixture $name" }
            .readText()

    @Test
    fun manifestFixtureParses() {
        val manifest = json.decodeFromString<ManifestDto>(resource("manifest.json"))
        val item = manifest.items.single()
        assertEquals("5f6f6cfa-8a59-4e2e-9a69-1a1f9f7f2c10", item.id)
        assertEquals(7, item.version)
        assertEquals(listOf("AI", "记忆"), item.tags)
        assertEquals("audio", item.files.first().kind)
        assertEquals("42", manifest.nextCursor)
        assertEquals(false, manifest.hasMore)
        assertEquals("e2a0c4f8-6b3d-4f21-9a7e-5c8d0b1a2f39", manifest.epoch)
        assertEquals(1793516400000, manifest.tombstones.single().deletedAt)
        assertEquals(manifest.epoch, manifest.tombstones.single().epoch)
    }

    @Test
    fun stateFixtureParses() {
        val state = json.decodeFromString<SyncStateDto>(resource("state.json"))
        assertEquals(2, state.items.size)
        assertEquals(642.25, state.items.first().audioPositionSec, 0.0)
        assertTrue(state.items[1].bookLocator!!.contains("chapter_index"))
        assertEquals("20", state.nextCursor)
        assertTrue(state.hasMore)
        assertEquals("e2a0c4f8-6b3d-4f21-9a7e-5c8d0b1a2f39", state.epoch)
        assertEquals("in_progress", state.items.first().consumptionState)
        assertEquals(19L, state.items.first().stateSeq)
        assertEquals(1793516400000, state.items.first().lastConsumedAt)
    }

    @Test
    fun fileFixtureParses() {
        val file = json.decodeFromString<SyncFileDto>(resource("file.json"))
        assertEquals("transcript", file.kind)
        assertEquals(184320L, file.size)
        assertEquals(7, file.version)
    }

    @Test
    fun errorFixtureParses() {
        val error = json.decodeFromString<ApiErrorBody>(resource("error.json"))
        assertEquals("auth.device_revoked", error.code)
        assertEquals("Device authorization has been revoked", error.message)
        assertNull(error.details)
    }

    @Test
    fun searchFixtureParsesEvidenceAndItem() {
        val search = json.decodeFromString<SearchResponseDto>(resource("search.json"))
        val result = search.results.single()
        assertEquals("5f6f6cfa-8a59-4e2e-9a69-1a1f9f7f2c10", result.item.id)
        assertEquals(listOf("AI", "记忆"), result.item.tags)
        assertEquals("transcript", result.evidence.single().docKind)
        assertEquals("3:65000", result.evidence.single().ref)
        assertEquals(
            "/items/5f6f6cfa-8a59-4e2e-9a69-1a1f9f7f2c10/listen#segment-3",
            result.evidence.single().url,
        )
        assertEquals("Video", result.item.sourceTypeLabel)
        assertEquals("In progress", result.item.consumptionLabel)
        assertEquals("Completed", result.item.processingLabel)
        assertTrue(result.item.hasCover)
        assertEquals(setOf("audio", "cover"), result.item.artifacts.map { it.kind }.toSet())
        assertEquals(
            "/api/items/5f6f6cfa-8a59-4e2e-9a69-1a1f9f7f2c10/audio",
            result.item.artifacts.first { it.kind == "audio" }.url,
        )
        assertEquals(1, search.count)
    }

    @Test
    fun mutationFixtureParsesCanonicalFieldsAndClocks() {
        val mutation = json.decodeFromString<MutationResponseDto>(resource("mutation.json"))
        assertEquals(false, mutation.applied)
        assertEquals(8, mutation.item.version)
        assertEquals("host-wins", mutation.item.tags.last())
        assertEquals("device-1", mutation.fieldClocks["tags"]!!.deviceId)
        assertEquals(listOf("sync.clock_skew"), mutation.warnings)
    }

    @Test
    fun healthFixtureParsesCapabilities() {
        val health = json.decodeFromString<HealthDto>(resource("health.json"))
        assertEquals("0.1.0", health.apiVersion)
        assertEquals(true, health.capabilities["sync"])
        assertEquals(true, health.capabilities["device_tokens"])
        assertEquals(true, health.capabilities["file_download"])
    }

    @Test
    fun inspectFixtureParsesCollectionPreview() {
        val inspect = json.decodeFromString<LinkInspectResponseDto>(resource("inspect.json"))
        assertEquals("collection", inspect.kind)
        assertEquals(2, inspect.episodeCount)
        assertEquals("Episode One", inspect.episodes.first().title)
        assertEquals(120.0, inspect.totalDurationSec ?: 0.0, 0.0)
        assertTrue(inspect.warnings.isEmpty())
    }

    @Test
    fun collectionFixtureParsesEpisodes() {
        val collection = json.decodeFromString<CollectionDto>(resource("collection.json"))
        assertEquals("Fixture Collection", collection.title)
        assertEquals(2, collection.episodeCount)
        assertEquals(2, collection.status.queued)
        assertEquals(1, collection.items.first().collectionIndex)
        assertEquals("Episode Two", collection.items[1].title)
    }
}
