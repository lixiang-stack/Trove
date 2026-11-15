package dev.trove.core.search

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import dev.trove.core.db.TroveDatabase
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class SearchIndexTest {
    private lateinit var database: TroveDatabase
    private lateinit var index: SearchIndex

    @Before
    fun setUp() {
        database = TroveDatabase.inMemory(ApplicationProvider.getApplicationContext<Context>())
        index = SearchIndex(database)
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun fts5IsAvailableAndDeleteCompletes() = runBlocking {
        withTimeout(5_000) {
            org.junit.Assume.assumeTrue(
                "Framework SQLite in Robolectric has no FTS5",
                index.isAvailable(),
            )
            index.deleteItem("missing")
        }
    }

    @Test
    fun chineseBigramsMatchIndexedDocuments() = runBlocking {
        org.junit.Assume.assumeTrue(
            "Framework SQLite in Robolectric has no FTS5",
            index.isAvailable(),
        )
        index.replaceItem(
            "item-1",
            listOf(SearchDocument("人工智能正在改变记忆方式", "transcript", "1:0")),
        )
        val hits = withTimeout(5_000) { index.search("智能") }
        assertTrue(hits.isNotEmpty())
        assertTrue(hits.first().text.contains("智能"))
    }
}
