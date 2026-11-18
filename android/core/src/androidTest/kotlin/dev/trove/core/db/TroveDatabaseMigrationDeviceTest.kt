package dev.trove.core.db

import android.database.sqlite.SQLiteDatabase
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Device-only migration check for the production bundled SQLite driver.
 *
 * The JVM migration test opens the database through the framework SQLite helper,
 * which takes a different Room code path. This builds a real version-3 database
 * from the exported schema and opens it through [TroveDatabase.create], so a
 * migration that only implements the SupportSQLiteDatabase API fails here.
 */
@RunWith(AndroidJUnit4::class)
class TroveDatabaseMigrationDeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext

    @Before
    fun setUp() {
        context.deleteDatabase(TroveDatabase.NAME)
    }

    @After
    fun tearDown() {
        context.deleteDatabase(TroveDatabase.NAME)
    }

    @Test
    fun bundledDriverMigratesVersion3DatabaseAndPreservesRows() = runBlocking {
        createVersion3Database()

        val database = TroveDatabase.create(context)
        try {
            val item = database.itemDao().find("legacy-item")
            assertEquals("Before migration", item?.title)
            assertNull(item?.collectionId)
        } finally {
            database.close()
        }
    }

    private fun createVersion3Database() {
        val file = context.getDatabasePath(TroveDatabase.NAME)
        file.parentFile?.mkdirs()
        val legacy = SQLiteDatabase.openOrCreateDatabase(file, null)
        try {
            val schema = JSONObject(
                instrumentation.context.assets
                    .open("dev.trove.core.db.TroveDatabase/3.json")
                    .bufferedReader()
                    .use { it.readText() }
            ).getJSONObject("database")
            val entities = schema.getJSONArray("entities")
            for (index in 0 until entities.length()) {
                val entity = entities.getJSONObject(index)
                val table = entity.getString("tableName")
                legacy.execSQL(entity.getString("createSql").replace("\${TABLE_NAME}", table))
                val indices = entity.optJSONArray("indices") ?: continue
                for (indexIndex in 0 until indices.length()) {
                    legacy.execSQL(
                        indices.getJSONObject(indexIndex)
                            .getString("createSql")
                            .replace("\${TABLE_NAME}", table)
                    )
                }
            }
            val setupQueries = schema.getJSONArray("setupQueries")
            for (index in 0 until setupQueries.length()) {
                legacy.execSQL(setupQueries.getString(index))
            }
            legacy.execSQL(
                """
                INSERT INTO items (
                    id, version, source_type, platform, title, fetched_at,
                    processing_state, has_audio, has_book, consumption_state,
                    audio_position_sec, content_seq, state_seq, download_state,
                    last_synced_at
                ) VALUES (
                    'legacy-item', 1, 'video_url', 'youtube', 'Before migration', 1,
                    'completed', 1, 0, 'unstarted',
                    0, 1, 1, 'none',
                    1
                )
                """.trimIndent()
            )
            legacy.version = 3
        } finally {
            legacy.close()
        }
    }
}
