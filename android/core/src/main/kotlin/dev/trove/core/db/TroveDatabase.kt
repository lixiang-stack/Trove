package dev.trove.core.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.sqlite.driver.bundled.BundledSQLiteDriver

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
    ],
    version = 3,
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

    companion object {
        const val NAME = "trove.db"

        val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    "ALTER TABLE artifacts ADD COLUMN downloaded_bytes INTEGER NOT NULL DEFAULT 0"
                )
                db.execSQL(
                    "UPDATE artifacts SET downloaded_bytes = size WHERE download_state = 'completed'"
                )
                db.execSQL("ALTER TABLE artifacts ADD COLUMN etag TEXT")
                db.execSQL("ALTER TABLE artifacts ADD COLUMN error_code TEXT")
                db.execSQL(
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
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(SearchFtsSchema.CREATE)
            }
        }

        fun create(context: Context): TroveDatabase =
            Room.databaseBuilder(context, TroveDatabase::class.java, NAME)
                .setDriver(BundledSQLiteDriver())
                .addMigrations(MIGRATION_1_2, MIGRATION_2_3)
                .build()

        fun inMemory(context: Context): TroveDatabase =
            Room.inMemoryDatabaseBuilder(context, TroveDatabase::class.java)
                .allowMainThreadQueries()
                .build()
    }
}
