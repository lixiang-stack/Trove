package dev.trove.core.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.SQLiteConnection
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.sqlite.driver.bundled.BundledSQLiteDriver
import androidx.sqlite.execSQL

@Database(
    entities = [
        ItemEntity::class,
        ArtifactEntity::class,
        TranscriptSegmentEntity::class,
        BookChapterEntity::class,
        BookParagraphEntity::class,
        TagEntity::class,
        ItemTagEntity::class,
        SyncCursorEntity::class,
        PendingMutationEntity::class,
        PendingDeletionEntity::class,
        CollectionDownloadIntentEntity::class,
    ],
    version = 6,
    exportSchema = true,
)
abstract class TroveDatabase : RoomDatabase() {
    abstract fun itemDao(): ItemDao

    abstract fun artifactDao(): ArtifactDao

    abstract fun tagDao(): TagDao

    abstract fun transcriptSegmentDao(): TranscriptSegmentDao

    abstract fun bookDao(): BookDao

    abstract fun syncCursorDao(): SyncCursorDao

    abstract fun pendingMutationDao(): PendingMutationDao

    abstract fun pendingDeletionDao(): PendingDeletionDao

    abstract fun collectionDownloadIntentDao(): CollectionDownloadIntentDao

    companion object {
        const val NAME = "trove.db"

        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) = migrate { db.execSQL(it) }

            override fun migrate(connection: SQLiteConnection) = migrate { connection.execSQL(it) }

            private fun migrate(execSQL: (String) -> Unit) {
                execSQL(
                    "ALTER TABLE artifacts ADD COLUMN downloaded_bytes INTEGER NOT NULL DEFAULT 0"
                )
                execSQL(
                    "UPDATE artifacts SET downloaded_bytes = size WHERE download_state = 'completed'"
                )
                execSQL("ALTER TABLE artifacts ADD COLUMN etag TEXT")
                execSQL("ALTER TABLE artifacts ADD COLUMN error_code TEXT")
                execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS pending_deletions (
                        path TEXT NOT NULL PRIMARY KEY,
                        item_id TEXT NOT NULL
                    )
                    """.trimIndent()
                )
            }
        }

        val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) = migrate { db.execSQL(it) }

            override fun migrate(connection: SQLiteConnection) = migrate { connection.execSQL(it) }

            private fun migrate(execSQL: (String) -> Unit) {
                execSQL(SearchFtsSchema.CREATE)
            }
        }

        val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) = migrate { db.execSQL(it) }

            override fun migrate(connection: SQLiteConnection) = migrate { connection.execSQL(it) }

            private fun migrate(execSQL: (String) -> Unit) {
                execSQL("ALTER TABLE items ADD COLUMN collection_id TEXT")
                execSQL("ALTER TABLE items ADD COLUMN collection_index INTEGER")
                execSQL("ALTER TABLE items ADD COLUMN collection_title TEXT")
                execSQL("ALTER TABLE items ADD COLUMN collection_platform TEXT")
                execSQL("ALTER TABLE items ADD COLUMN collection_source_url TEXT")
            }
        }

        val MIGRATION_4_5 = object : Migration(4, 5) {
            override fun migrate(db: SupportSQLiteDatabase) = migrate { db.execSQL(it) }

            override fun migrate(connection: SQLiteConnection) = migrate { connection.execSQL(it) }

            private fun migrate(execSQL: (String) -> Unit) {
                execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS collection_download_intents (
                        collection_id TEXT NOT NULL PRIMARY KEY
                    )
                    """.trimIndent()
                )
            }
        }

        val MIGRATION_5_6 = object : Migration(5, 6) {
            override fun migrate(db: SupportSQLiteDatabase) = migrate { db.execSQL(it) }

            override fun migrate(connection: SQLiteConnection) = migrate { connection.execSQL(it) }

            private fun migrate(execSQL: (String) -> Unit) {
                execSQL("ALTER TABLE items ADD COLUMN source_url_raw TEXT")
            }
        }

        fun create(context: Context): TroveDatabase =
            Room.databaseBuilder(context, TroveDatabase::class.java, NAME)
                .setDriver(BundledSQLiteDriver())
                .addMigrations(
                    MIGRATION_1_2,
                    MIGRATION_2_3,
                    MIGRATION_3_4,
                    MIGRATION_4_5,
                    MIGRATION_5_6,
                )
                .build()

        fun inMemory(context: Context): TroveDatabase =
            Room.inMemoryDatabaseBuilder(context, TroveDatabase::class.java)
                .allowMainThreadQueries()
                .build()
    }
}
