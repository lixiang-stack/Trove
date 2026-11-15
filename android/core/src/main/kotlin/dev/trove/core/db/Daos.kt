package dev.trove.core.db

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface ItemDao {
    @Query("SELECT * FROM items WHERE id = :id")
    suspend fun find(id: String): ItemEntity?

    @Query("SELECT * FROM items ORDER BY fetched_at DESC, id DESC")
    fun observeAll(): Flow<List<ItemEntity>>

    @Query("SELECT COUNT(*) FROM items")
    suspend fun count(): Int

    @Upsert
    suspend fun upsert(item: ItemEntity)

    @Query("DELETE FROM items WHERE id = :id")
    suspend fun delete(id: String)
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

    @Upsert
    suspend fun upsert(mutation: PendingMutationEntity)

    @Query("DELETE FROM pending_mutations WHERE idempotency_key = :key")
    suspend fun delete(key: String)
}
