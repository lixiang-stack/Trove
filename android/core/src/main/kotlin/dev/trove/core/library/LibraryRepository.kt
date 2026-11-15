package dev.trove.core.library

import dev.trove.core.db.TroveDatabase
import dev.trove.core.db.writeTransaction
import dev.trove.core.storage.ArtifactFileStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

class LibraryRepository(
    private val database: TroveDatabase,
    private val fileStore: ArtifactFileStore,
) {
    fun observeLibrary(): Flow<List<LibraryItem>> =
        database.itemDao().observeLibrary().map { rows -> rows.map { it.toLibraryItem() } }

    fun observeItem(itemId: String): Flow<LibraryItem?> =
        database.itemDao().observeDetails(itemId).map { it?.toLibraryItem() }

    fun observeDownloads(): Flow<List<LibraryItem>> =
        database.itemDao().observeWithDownloads().map { rows -> rows.map { it.toLibraryItem() } }

    suspend fun find(itemId: String): LibraryItem? =
        database.itemDao().findDetails(itemId)?.toLibraryItem()

    suspend fun deleteLocalItem(itemId: String) {
        val artifacts = database.artifactDao().forItem(itemId)
        database.writeTransaction {
            database.pendingDeletionDao().deleteForItem(itemId)
            database.itemDao().delete(itemId)
        }
        artifacts.forEach { artifact ->
            fileStore.deleteArtifact(itemId, artifact.kind, artifact.localPath)
        }
        fileStore.deleteItem(itemId)
    }

    suspend fun cleanupPendingFiles(playingItemId: String?) {
        val pending = database.pendingDeletionDao().all()
        if (pending.isEmpty()) return
        val removable = pending.filter { it.itemId != playingItemId }
        removable.forEach { fileStore.deletePath(it.path) }
        if (removable.isNotEmpty()) {
            database.pendingDeletionDao().deletePaths(removable.map { it.path })
        }
    }
}
