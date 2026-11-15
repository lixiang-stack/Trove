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
}
