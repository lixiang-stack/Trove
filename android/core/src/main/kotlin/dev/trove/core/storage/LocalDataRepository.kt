package dev.trove.core.storage

import dev.trove.core.db.TroveDatabase
import dev.trove.core.search.SearchIndex
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class LocalDataRepository(
    private val database: TroveDatabase,
    private val fileStore: ArtifactFileStore,
    private val searchIndex: SearchIndex,
) {
    suspend fun clearAll() = withContext(Dispatchers.IO) {
        val ids = database.itemDao().allIds()
        for (id in ids) {
            fileStore.deleteItem(id)
        }
        runCatching { searchIndex.clear() }
        database.clearAllTables()
    }

    suspend fun downloadedBytes(): Long = database.artifactDao().completedBytes()

    suspend fun downloadQueueSize(): Int = database.artifactDao().itemsWithPendingDownloads().size

    fun availableBytes(): Long = fileStore.usableSpace()
}
