package dev.trove.core.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface ItemDao {
    @Query("SELECT * FROM items WHERE id = :id")
    suspend fun find(id: String): ItemEntity?

    @Transaction
    @Query("SELECT * FROM items WHERE id = :id")
    suspend fun findDetails(id: String): ItemWithDetails?

    @Transaction
    @Query("SELECT * FROM items WHERE id = :id")
    fun observeDetails(id: String): Flow<ItemWithDetails?>

    @Query("SELECT * FROM items ORDER BY fetched_at DESC, id DESC")
    fun observeAll(): Flow<List<ItemEntity>>

    @Transaction
    @Query("SELECT * FROM items ORDER BY fetched_at DESC, id DESC")
    fun observeLibrary(): Flow<List<ItemWithDetails>>

    @Transaction
    @Query(
        """
        SELECT * FROM items
        WHERE EXISTS (
            SELECT 1 FROM artifacts
            WHERE artifacts.item_id = items.id AND artifacts.download_state != 'none'
        )
        ORDER BY fetched_at DESC, id DESC
        """
    )
    fun observeWithDownloads(): Flow<List<ItemWithDetails>>

    @Query("SELECT id FROM items")
    suspend fun allIds(): List<String>

    @Query("SELECT COUNT(*) FROM items")
    suspend fun count(): Int

    @Upsert
    suspend fun upsert(item: ItemEntity)

    @Query("DELETE FROM items WHERE id = :id")
    suspend fun delete(id: String)

    @Query(
        """
        UPDATE items SET
            audio_position_sec = :positionSec,
            book_locator = :bookLocator,
            consumption_state = :consumptionState,
            last_consumed_at = :lastConsumedAt,
            state_seq = :stateSeq
        WHERE id = :id AND state_seq < :stateSeq
        """
    )
    suspend fun applyState(
        id: String,
        positionSec: Double,
        bookLocator: String?,
        consumptionState: String,
        lastConsumedAt: Long?,
        stateSeq: Long,
    ): Int

    @Query(
        """
        UPDATE items SET
            audio_position_sec = :positionSec,
            consumption_state = :consumptionState,
            last_consumed_at = :lastConsumedAt
        WHERE id = :id
        """
    )
    suspend fun applyLocalProgress(
        id: String,
        positionSec: Double,
        consumptionState: String,
        lastConsumedAt: Long,
    )

    @Query(
        """
        UPDATE items SET
            book_locator = :bookLocator,
            consumption_state = :consumptionState,
            last_consumed_at = :lastConsumedAt
        WHERE id = :id
        """
    )
    suspend fun applyLocalBookProgress(
        id: String,
        bookLocator: String,
        consumptionState: String,
        lastConsumedAt: Long,
    )

    @Query(
        """
        UPDATE items SET
            consumption_state = :consumptionState,
            last_consumed_at = :lastConsumedAt
        WHERE id = :id
        """
    )
    suspend fun applyLocalConsumption(
        id: String,
        consumptionState: String,
        lastConsumedAt: Long,
    )

    @Query(
        """
        UPDATE items SET
            version = :version,
            audio_position_sec = :positionSec,
            book_locator = :bookLocator,
            consumption_state = :consumptionState
        WHERE id = :id
        """
    )
    suspend fun applyCanonical(
        id: String,
        version: Int,
        positionSec: Double,
        bookLocator: String?,
        consumptionState: String,
    )
}

@Dao
interface ArtifactDao {
    @Query("SELECT * FROM artifacts WHERE item_id = :itemId ORDER BY kind")
    suspend fun forItem(itemId: String): List<ArtifactEntity>

    @Query("SELECT * FROM artifacts WHERE item_id = :itemId AND kind = :kind")
    suspend fun find(itemId: String, kind: String): ArtifactEntity?

    @Upsert
    suspend fun upsert(artifact: ArtifactEntity)

    @Query("DELETE FROM artifacts WHERE item_id = :itemId AND kind = :kind")
    suspend fun delete(itemId: String, kind: String)

    @Query(
        """
        UPDATE artifacts SET download_state = :state, error_code = :errorCode
        WHERE item_id = :itemId AND kind = :kind
        """
    )
    suspend fun setDownloadState(
        itemId: String,
        kind: String,
        state: String,
        errorCode: String?,
    )

    @Query(
        """
        UPDATE artifacts SET
            download_state = :state,
            downloaded_bytes = :downloadedBytes,
            etag = :etag,
            error_code = :errorCode
        WHERE item_id = :itemId AND kind = :kind
        """
    )
    suspend fun updateProgress(
        itemId: String,
        kind: String,
        state: String,
        downloadedBytes: Long,
        etag: String?,
        errorCode: String?,
    )

    @Query("SELECT COALESCE(SUM(size), 0) FROM artifacts WHERE download_state = 'completed'")
    suspend fun completedBytes(): Long

    @Query(
        """
        SELECT DISTINCT item_id FROM artifacts
        WHERE download_state IN ('queued', 'downloading')
        ORDER BY item_id
        """
    )
    suspend fun itemsWithPendingDownloads(): List<String>

    @Query(
        """
        UPDATE artifacts SET download_state = 'failed', error_code = :code
        WHERE item_id = :itemId AND download_state IN ('queued', 'downloading')
        """
    )
    suspend fun markPendingFailed(itemId: String, code: String)
}

@Dao
interface TagDao {
    @Upsert
    suspend fun upsertAll(tags: List<TagEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertItemTags(tags: List<ItemTagEntity>)

    @Query("DELETE FROM item_tags WHERE item_id = :itemId")
    suspend fun clearItemTags(itemId: String)
}

@Dao
interface TranscriptSegmentDao {
    @Query("SELECT * FROM transcript_segments WHERE item_id = :itemId ORDER BY seq")
    fun observeForItem(itemId: String): Flow<List<TranscriptSegmentEntity>>

    @Query("SELECT * FROM transcript_segments WHERE item_id = :itemId ORDER BY seq")
    suspend fun forItem(itemId: String): List<TranscriptSegmentEntity>

    @Query("SELECT COUNT(*) FROM transcript_segments WHERE item_id = :itemId")
    suspend fun countForItem(itemId: String): Int

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(segments: List<TranscriptSegmentEntity>)

    @Query("DELETE FROM transcript_segments WHERE item_id = :itemId")
    suspend fun deleteForItem(itemId: String)
}

@Dao
interface BookDao {
    @Query("SELECT * FROM book_chapters WHERE item_id = :itemId ORDER BY chapter_index")
    fun observeChapters(itemId: String): Flow<List<BookChapterEntity>>

    @Query("SELECT * FROM book_chapters WHERE item_id = :itemId ORDER BY chapter_index")
    suspend fun chapters(itemId: String): List<BookChapterEntity>

    @Query(
        "SELECT * FROM book_chapters WHERE item_id = :itemId AND chapter_index = :chapterIndex"
    )
    suspend fun chapter(itemId: String, chapterIndex: Int): BookChapterEntity?

    @Query("SELECT COUNT(*) FROM book_chapters WHERE item_id = :itemId")
    suspend fun chapterCount(itemId: String): Int

    @Query(
        "SELECT * FROM book_paragraphs WHERE item_id = :itemId ORDER BY chapter_index, paragraph_index"
    )
    suspend fun paragraphs(itemId: String): List<BookParagraphEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertChapters(chapters: List<BookChapterEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertParagraphs(paragraphs: List<BookParagraphEntity>)

    @Query("DELETE FROM book_chapters WHERE item_id = :itemId")
    suspend fun deleteForItem(itemId: String)

    @Query("DELETE FROM book_paragraphs WHERE item_id = :itemId")
    suspend fun deleteParagraphsForItem(itemId: String)
}

@Dao
interface SyncCursorDao {
    @Query("SELECT * FROM sync_cursor WHERE id = 1")
    suspend fun current(): SyncCursorEntity?

    @Upsert
    suspend fun upsert(cursor: SyncCursorEntity)
}

@Dao
interface PendingMutationDao {
    @Query("SELECT * FROM pending_mutations ORDER BY created_at, idempotency_key")
    suspend fun pending(): List<PendingMutationEntity>

    @Query("SELECT * FROM pending_mutations WHERE idempotency_key = :key")
    suspend fun find(key: String): PendingMutationEntity?

    @Query("SELECT COUNT(*) FROM pending_mutations")
    suspend fun count(): Int

    @Upsert
    suspend fun upsert(mutation: PendingMutationEntity)

    @Query("DELETE FROM pending_mutations WHERE idempotency_key = :key")
    suspend fun delete(key: String)

    @Query("DELETE FROM pending_mutations WHERE item_id = :itemId AND field = :field")
    suspend fun deleteForField(itemId: String, field: String)

    @Query(
        """
        UPDATE pending_mutations SET retry_count = retry_count + 1, last_error = :error
        WHERE idempotency_key = :key
        """
    )
    suspend fun markFailed(key: String, error: String)
}

@Dao
interface PendingDeletionDao {
    @Query("SELECT * FROM pending_deletions")
    suspend fun all(): List<PendingDeletionEntity>

    @Upsert
    suspend fun upsertAll(deletions: List<PendingDeletionEntity>)

    @Query("DELETE FROM pending_deletions WHERE path IN (:paths)")
    suspend fun deletePaths(paths: List<String>)

    @Query("DELETE FROM pending_deletions WHERE item_id = :itemId")
    suspend fun deleteForItem(itemId: String)
}
