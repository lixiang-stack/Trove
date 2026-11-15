package dev.trove.core.db

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
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
    ],
    version = 1,
    exportSchema = true,
)
abstract class TroveDatabase : RoomDatabase() {
    abstract fun itemDao(): ItemDao

    abstract fun syncCursorDao(): SyncCursorDao

    abstract fun pendingMutationDao(): PendingMutationDao

    companion object {
        const val NAME = "trove.db"

        fun create(context: Context): TroveDatabase =
            Room.databaseBuilder(context, TroveDatabase::class.java, NAME)
                .setDriver(BundledSQLiteDriver())
                .build()

        fun inMemory(context: Context): TroveDatabase =
            Room.inMemoryDatabaseBuilder(context, TroveDatabase::class.java)
                .allowMainThreadQueries()
                .build()
    }
}
