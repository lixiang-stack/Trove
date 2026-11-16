package dev.trove.core.search

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import dev.trove.core.db.TroveDatabase
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SearchIndexDeviceTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private lateinit var database: TroveDatabase
    private lateinit var index: SearchIndex

    @Before
    fun setUp() {
        context.deleteDatabase(TroveDatabase.NAME)
        database = TroveDatabase.create(context)
        index = SearchIndex(database)
    }

    @After
    fun tearDown() {
        database.close()
        context.deleteDatabase(TroveDatabase.NAME)
    }

    @Test
    fun bundledSqliteSupportsFts5AndChineseBigrams() = runBlocking {
        assertTrue(index.isAvailable())
        index.replaceItem(
            "item-1",
            listOf(
                SearchDocument("人工智能正在改变记忆方式", "transcript", "1:0"),
                SearchDocument("The quick brown foxes", "book", "0:0"),
            ),
        )
        val chinese = index.search("智能")
        assertTrue(chinese.isNotEmpty())
        assertTrue(chinese.first().text.contains("智能"))

        val english = index.search("fox")
        assertTrue(english.isNotEmpty())
    }

    @Test
    fun thousandItemSearchP95IsUnderOneSecond() = runBlocking {
        assertTrue(index.isAvailable())
        for (number in 0 until 1_000) {
            index.replaceItem(
                "item-$number",
                listOf(
                    SearchDocument(
                        "第 $number 条记忆：人工智能正在改变记忆方式，智能体需要上下文。",
                        "transcript",
                        "1:0",
                    )
                ),
            )
        }

        val durations = (0 until 20).map {
            kotlin.system.measureTimeMillis {
                index.search("智能", limit = 1_000)
            }
        }.sorted()
        val p95 = durations[(durations.size * 0.95).toInt().coerceAtMost(durations.lastIndex)]
        assertTrue("p95=${p95}ms durations=$durations", p95 < 1_000)
    }
}
