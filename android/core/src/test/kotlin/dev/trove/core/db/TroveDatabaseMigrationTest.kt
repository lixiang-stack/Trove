package dev.trove.core.db

import androidx.room.testing.MigrationTestHelper
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class TroveDatabaseMigrationTest {
    @get:Rule
    val helper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        TroveDatabase::class.java,
        emptyList(),
        FrameworkSQLiteOpenHelperFactory(),
    )

    @After
    fun tearDown() {
        InstrumentationRegistry.getInstrumentation()
            .targetContext
            .deleteDatabase(TEST_DB)
    }

    @Test
    fun migration3To4AddsCollectionColumnsAndPreservesRows() {
        helper.createDatabase(TEST_DB, 3).use { database ->
            database.execSQL(
                """
                INSERT INTO items (
                    id, version, source_type, platform, title, fetched_at,
                    processing_state, has_audio, has_book, consumption_state,
                    audio_position_sec, content_seq, state_seq, download_state,
                    last_synced_at
                ) VALUES (
                    'item-1', 1, 'video_url', 'youtube', 'Before migration', 1,
                    'completed', 1, 0, 'unstarted',
                    0, 1, 1, 'none',
                    1
                )
                """.trimIndent()
            )
        }

        val migrated = helper.runMigrationsAndValidate(
            TEST_DB,
            4,
            true,
            TroveDatabase.MIGRATION_3_4,
        )
        migrated.use { database ->
            val columns = mutableSetOf<String>()
            database.query("PRAGMA table_info(items)").use { cursor ->
                while (cursor.moveToNext()) {
                    columns += cursor.getString(cursor.getColumnIndexOrThrow("name"))
                }
            }
            assertTrue(
                columns.containsAll(
                    setOf(
                        "collection_id",
                        "collection_index",
                        "collection_title",
                        "collection_platform",
                        "collection_source_url",
                    )
                )
            )
            database.query("SELECT title FROM items WHERE id = 'item-1'").use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals("Before migration", cursor.getString(0))
            }
        }
    }

    @Test
    fun migration4To5CreatesCollectionDownloadIntents() {
        helper.createDatabase(TEST_DB, 4).use { }

        val migrated = helper.runMigrationsAndValidate(
            TEST_DB,
            5,
            true,
            TroveDatabase.MIGRATION_4_5,
        )
        migrated.use { database ->
            database.execSQL(
                "INSERT INTO collection_download_intents (collection_id) VALUES ('collection-1')"
            )
            database.query("SELECT collection_id FROM collection_download_intents").use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals("collection-1", cursor.getString(0))
            }
        }
    }

    @Test
    fun migration5To6AddsSourceUrlRaw() {
        helper.createDatabase(TEST_DB, 5).use { database ->
            database.execSQL(
                """
                INSERT INTO items (
                    id, version, source_type, platform, title, fetched_at,
                    processing_state, has_audio, has_book, consumption_state,
                    audio_position_sec, content_seq, state_seq, download_state,
                    last_synced_at
                ) VALUES (
                    'item-1', 1, 'video_url', 'youtube', 'Before migration', 1,
                    'completed', 1, 0, 'unstarted',
                    0, 1, 1, 'none',
                    1
                )
                """.trimIndent()
            )
        }

        val migrated = helper.runMigrationsAndValidate(
            TEST_DB,
            6,
            true,
            TroveDatabase.MIGRATION_5_6,
        )
        migrated.use { database ->
            val columns = mutableSetOf<String>()
            database.query("PRAGMA table_info(items)").use { cursor ->
                while (cursor.moveToNext()) {
                    columns += cursor.getString(cursor.getColumnIndexOrThrow("name"))
                }
            }
            assertTrue(columns.contains("source_url_raw"))
            database.query("SELECT title FROM items WHERE id = 'item-1'").use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals("Before migration", cursor.getString(0))
            }
        }
    }

    private companion object {
        const val TEST_DB = "trove-migration-test.db"
    }
}
