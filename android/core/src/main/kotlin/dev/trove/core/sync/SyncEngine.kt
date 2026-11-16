package dev.trove.core.sync

import dev.trove.core.db.ArtifactEntity
import dev.trove.core.db.ItemEntity
import dev.trove.core.db.ItemTagEntity
import dev.trove.core.db.PendingDeletionEntity
import dev.trove.core.db.PendingMutationEntity
import dev.trove.core.db.SyncCursorEntity
import dev.trove.core.db.TagEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.db.writeTransaction
import dev.trove.core.library.ItemMutationRepository
import dev.trove.core.network.ManifestDto
import dev.trove.core.network.MutationItemDto
import dev.trove.core.network.ProgressRequestDto
import dev.trove.core.network.SyncItemDto
import dev.trove.core.network.SyncStateDto
import dev.trove.core.network.TagsRequestDto
import dev.trove.core.network.TroveApiException
import dev.trove.core.network.TroveClient
import dev.trove.core.network.TroveNetworkException
import dev.trove.core.network.TroveTlsException
import dev.trove.core.storage.ArtifactFileStore
import dev.trove.core.tags.normalizeTags
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.Json

const val CURSOR_INVALID = "sync.cursor_invalid"
private const val OFFLINE_CODE = "sync.offline"

sealed interface SyncStatus {
    val lastSuccessAt: Long?

    data class Idle(override val lastSuccessAt: Long?) : SyncStatus

    data class Syncing(override val lastSuccessAt: Long?) : SyncStatus

    data class Offline(override val lastSuccessAt: Long?) : SyncStatus

    data class Error(
        val code: String,
        val message: String,
        override val lastSuccessAt: Long?,
    ) : SyncStatus
}

data class SyncResult(
    val success: Boolean,
    val pendingMutations: Int = 0,
    val errorCode: String? = null,
)

fun interface SyncClientProvider {
    fun client(): TroveClient?
}

fun interface DownloadQueue {
    suspend fun enqueue(itemId: String)
}

class SyncEngine(
    private val database: TroveDatabase,
    private val clientProvider: SyncClientProvider,
    private val fileStore: ArtifactFileStore,
    private val downloadQueue: DownloadQueue? = null,
    private val pageSize: Int = 100,
    private val now: () -> Long = System::currentTimeMillis,
    private val nowPlayingItemId: () -> String? = { null },
    private val onItemChanged: suspend (String) -> Unit = {},
) {
    private val json = Json { ignoreUnknownKeys = true }
    private val mutex = Mutex()
    private val _status = MutableStateFlow<SyncStatus>(SyncStatus.Idle(null))
    val status: StateFlow<SyncStatus> = _status.asStateFlow()
    private val _conflicts = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val conflicts: SharedFlow<String> = _conflicts.asSharedFlow()

    suspend fun currentCursor() = database.syncCursorDao().current()

    suspend fun pendingMutationCount(): Int = database.pendingMutationDao().count()

    suspend fun lastPendingError(): String? = database.pendingMutationDao().lastError()

    suspend fun sync(): SyncResult = mutex.withLock {
        val previous = database.syncCursorDao().current()?.lastSuccessAt
        val client = clientProvider.client()
            ?: return@withLock fail("auth.required", "Not signed in", previous)
        _status.value = SyncStatus.Syncing(previous)
        try {
            guardedAttempt(client, previous)
        } catch (_: FullResyncRequired) {
            resetCursors()
            try {
                guardedAttempt(client, previous)
            } catch (_: FullResyncRequired) {
                fail(CURSOR_INVALID, "Sync cursor is invalid", previous)
            }
        }
    }

    private suspend fun guardedAttempt(client: TroveClient, previous: Long?): SyncResult =
        try {
            syncAttempt(client)
        } catch (error: TroveNetworkException) {
            offline(previous)
        } catch (_: TroveTlsException) {
            fail("network.tls", "TLS handshake failed", previous)
        } catch (error: TroveApiException) {
            fail(error.code, error.message, previous)
        }

    private suspend fun syncAttempt(client: TroveClient): SyncResult {
        val pushError = pushPending(client)
        syncManifest(client)
        val remaining = database.pendingMutationDao().count()
        if (remaining == 0 && pushError == null) {
            syncState(client)
        }
        if (pushError != null) {
            throw pushError
        }
        val successAt = now()
        saveCursor(lastSuccessAt = successAt, errorCode = null)
        _status.value = SyncStatus.Idle(successAt)
        return SyncResult(success = true, pendingMutations = remaining)
    }

    /**
     * Pushes every queued mutation, keeping failures for the next sync instead of
     * letting one poisoned mutation block content/tombstone pulls.
     */
    private suspend fun pushPending(client: TroveClient): TroveApiException? {
        var firstFailure: TroveApiException? = null
        val mutations = database.pendingMutationDao().pending()
        for (mutation in mutations) {
            try {
                pushMutation(client, mutation)
            } catch (error: TroveApiException) {
                if (error.statusCode == 401 || error.statusCode == 403) throw error
                if (firstFailure == null) firstFailure = error
            }
        }
        return firstFailure
    }

    private suspend fun pushMutation(client: TroveClient, mutation: PendingMutationEntity) {
        if (mutation.field == ItemMutationRepository.TAGS) {
            pushTags(client, mutation)
        } else {
            pushProgress(client, mutation)
        }
    }

    private suspend fun pushProgress(client: TroveClient, mutation: PendingMutationEntity) {
        val payload = runCatching {
            json.decodeFromString<ProgressRequestDto>(mutation.payloadJson)
        }.getOrNull()
        if (payload == null) {
            database.pendingMutationDao().delete(mutation.idempotencyKey)
            return
        }
        val response = try {
            client.progress(
                itemId = mutation.itemId,
                request = payload.copy(clientUpdatedAt = mutation.clientUpdatedAt),
                idempotencyKey = mutation.idempotencyKey,
            )
        } catch (error: TroveApiException) {
            if (error.statusCode == 404 || error.statusCode == 410) {
                database.pendingMutationDao().delete(mutation.idempotencyKey)
                return
            }
            database.pendingMutationDao().markFailed(mutation.idempotencyKey, error.code)
            throw error
        } catch (error: TroveNetworkException) {
            database.pendingMutationDao().markFailed(mutation.idempotencyKey, OFFLINE_CODE)
            throw error
        }
        val title = database.itemDao().find(mutation.itemId)?.title
        database.writeTransaction {
            val current = database.pendingMutationDao().find(mutation.idempotencyKey)
            if (current != null) {
                database.pendingMutationDao().delete(mutation.idempotencyKey)
                applyCanonicalProgress(response.item, payload)
            }
        }
        notifyWarnings(response.warnings)
        if (!response.applied) {
            _conflicts.tryEmit(conflictMessage(title))
        }
        indexChanged(mutation.itemId)
    }

    private suspend fun pushTags(client: TroveClient, mutation: PendingMutationEntity) {
        val payload = runCatching {
            json.decodeFromString<TagsRequestDto>(mutation.payloadJson)
        }.getOrNull()
        if (payload == null) {
            database.pendingMutationDao().delete(mutation.idempotencyKey)
            return
        }
        val response = try {
            client.tags(
                itemId = mutation.itemId,
                request = payload.copy(clientUpdatedAt = mutation.clientUpdatedAt),
                idempotencyKey = mutation.idempotencyKey,
            )
        } catch (error: TroveApiException) {
            if (error.statusCode == 404 || error.statusCode == 410) {
                database.pendingMutationDao().delete(mutation.idempotencyKey)
                return
            }
            database.pendingMutationDao().markFailed(mutation.idempotencyKey, error.code)
            throw error
        } catch (error: TroveNetworkException) {
            database.pendingMutationDao().markFailed(mutation.idempotencyKey, OFFLINE_CODE)
            throw error
        }
        val title = database.itemDao().find(mutation.itemId)?.title
        database.writeTransaction {
            val current = database.pendingMutationDao().find(mutation.idempotencyKey)
            if (current != null) {
                database.pendingMutationDao().delete(mutation.idempotencyKey)
                if (response.item.version > 0) {
                    database.itemDao().applyVersion(mutation.itemId, response.item.version)
                }
                if (!database.pendingMutationDao()
                        .hasPending(mutation.itemId, ItemMutationRepository.TAGS)
                ) {
                    replaceTags(mutation.itemId, response.item.tags)
                }
            }
        }
        notifyWarnings(response.warnings)
        if (!response.applied) {
            _conflicts.tryEmit(conflictMessage(title))
        }
        indexChanged(mutation.itemId)
    }

    private suspend fun replaceTags(itemId: String, tags: List<String>) {
        val normalized = runCatching { normalizeTags(tags) }.getOrNull() ?: return
        database.tagDao().clearItemTags(itemId)
        if (normalized.isEmpty()) return
        database.tagDao().upsertAll(
            normalized.map { TagEntity(normalizedName = it.normalizedName, name = it.name) }
        )
        database.tagDao().insertItemTags(
            normalized.map {
                ItemTagEntity(itemId = itemId, tagName = it.normalizedName, source = "user")
            }
        )
    }

    private fun conflictMessage(title: String?): String =
        if (title.isNullOrBlank()) {
            "已在其他设备更新，已使用最新值。"
        } else {
            "「$title」已在其他设备更新，已使用最新值。"
        }

    private fun blocksState(fields: Collection<String>): Boolean =
        fields.any { it != ItemMutationRepository.TAGS }

    private suspend fun indexChanged(itemId: String) {
        runCatching { onItemChanged(itemId) }
    }

    private fun notifyWarnings(warnings: List<String>) {
        if ("sync.clock_skew" in warnings) {
            _conflicts.tryEmit("设备时钟与 Host 相差较大，已按 Host 时间合并。")
        }
    }

    /**
     * Applies only the fields carried by the mutation and only when no newer
     * local mutation for the same field is still queued.
     */
    private suspend fun applyCanonicalProgress(
        item: MutationItemDto,
        payload: ProgressRequestDto,
    ) {
        if (item.version > 0) {
            database.itemDao().applyVersion(item.id, item.version)
        }
        val pending = database.pendingMutationDao().fieldsForItem(item.id).toSet()
        val statePending = blocksState(pending)
        if (payload.positionSec != null &&
            ItemMutationRepository.AUDIO_PROGRESS !in pending
        ) {
            database.itemDao().applyCanonicalAudioPosition(item.id, item.audioPositionSec)
        }
        if (payload.bookLocator != null &&
            ItemMutationRepository.BOOK_PROGRESS !in pending
        ) {
            database.itemDao().applyCanonicalBookLocator(item.id, item.bookLocator)
        }
        if (payload.consumptionState != null && !statePending) {
            database.itemDao().applyCanonicalConsumption(item.id, item.consumptionState)
        }
    }

    private suspend fun syncManifest(client: TroveClient) {
        val cursor = database.syncCursorDao().current()
        var contentCursor = cursor?.contentCursor
        var epoch = cursor?.epoch
        val seen = mutableSetOf<String>()
        val full = contentCursor == null
        var newItemSeen = false
        while (true) {
            val page = fetchManifest(client, contentCursor)
            if (epoch != null && page.epoch != epoch) throw FullResyncRequired()
            epoch = page.epoch
            newItemSeen = applyManifestPage(page, seen) || newItemSeen
            contentCursor = page.nextCursor
            // A full snapshot is only durable once every page has been applied:
            // otherwise a later page failure would turn the next sync into an
            // incremental one and skip deletion reconciliation.
            if (!full) {
                saveCursor(contentCursor = contentCursor, epoch = epoch)
            }
            if (!page.hasMore) break
        }
        if (full) {
            saveCursor(contentCursor = contentCursor, epoch = epoch)
            reconcileDeletedItems(seen)
        }
        if (newItemSeen) {
            clearStateCursor()
        }
    }

    private suspend fun clearStateCursor() {
        val current = database.syncCursorDao().current() ?: return
        database.syncCursorDao().upsert(current.copy(stateCursor = null))
    }

    private suspend fun fetchManifest(client: TroveClient, cursor: String?): ManifestDto =
        try {
            client.manifest(cursor = cursor, limit = pageSize)
        } catch (error: TroveApiException) {
            if (error.code == CURSOR_INVALID) throw FullResyncRequired()
            throw error
        }

    private suspend fun applyManifestPage(
        page: ManifestDto,
        seen: MutableSet<String>,
    ): Boolean {
        var newItemSeen = false
        for (item in page.items) {
            seen += item.id
            newItemSeen = applyManifestItem(item) || newItemSeen
        }
        for (tombstone in page.tombstones) {
            seen += tombstone.id
            deleteItem(tombstone.id, maximumVersion = tombstone.version)
        }
        return newItemSeen
    }

    private suspend fun applyManifestItem(dto: SyncItemDto): Boolean {
        val now = now()
        val filesToDelete = mutableListOf<Pair<String, String?>>()
        var needsDownload = false
        var isNew = false
        database.writeTransaction {
            val existing = database.itemDao().find(dto.id)
            isNew = existing == null
            database.itemDao().upsert(
                ItemEntity(
                    id = dto.id,
                    version = dto.version,
                    sourceType = dto.sourceType,
                    platform = dto.platform,
                    title = dto.title,
                    author = dto.author,
                    publishedAt = dto.publishedAt,
                    fetchedAt = dto.fetchedAt,
                    language = dto.language,
                    durationSec = dto.durationSec,
                    summary = dto.summary,
                    processingState = dto.processingState,
                    errorCode = dto.errorCode,
                    errorMessage = dto.errorMessage,
                    hasAudio = dto.hasAudio,
                    hasBook = dto.hasBook,
                    consumptionState = existing?.consumptionState ?: "unstarted",
                    audioPositionSec = existing?.audioPositionSec ?: 0.0,
                    bookLocator = existing?.bookLocator,
                    lastConsumedAt = existing?.lastConsumedAt,
                    contentSeq = existing?.contentSeq ?: 0,
                    stateSeq = existing?.stateSeq ?: 0,
                    downloadState = existing?.downloadState ?: "none",
                    lastSyncedAt = now,
                )
            )
            if (!database.pendingMutationDao().hasPending(dto.id, ItemMutationRepository.TAGS)) {
                applyTags(dto)
            }
            val existingArtifacts = database.artifactDao().forItem(dto.id).associateBy { it.kind }
            val kinds = dto.files.map { it.kind }.toSet()
            val outcome = applyArtifacts(dto, existingArtifacts, kinds)
            filesToDelete += outcome.filesToDelete
            needsDownload = outcome.needsDownload
        }
        cleanupRemovedArtifacts(dto.id, filesToDelete)
        if (needsDownload) {
            downloadQueue?.enqueue(dto.id)
        }
        indexChanged(dto.id)
        return isNew
    }

    private suspend fun applyTags(dto: SyncItemDto) {
        replaceTags(dto.id, dto.tags)
    }

    private suspend fun applyArtifacts(
        dto: SyncItemDto,
        existing: Map<String, ArtifactEntity>,
        currentKinds: Set<String>,
    ): ArtifactOutcome {
        val filesToDelete = mutableListOf<Pair<String, String?>>()
        var needsDownload = false
        val itemSelected = existing.values.any { it.downloadState != "none" }
        for (file in dto.files) {
            val previous = existing[file.kind]
            if (previous != null && previous.sha256 == file.sha256) {
                database.artifactDao().upsert(
                    previous.copy(
                        size = file.size,
                        mime = file.mime,
                        version = file.version,
                    )
                )
                continue
            }
            if (previous?.localPath != null) {
                filesToDelete += previous.kind to previous.localPath
            }
            if (file.kind == "transcript") {
                database.transcriptSegmentDao().deleteForItem(dto.id)
            }
            if (file.kind == "book_json") {
                database.bookDao().deleteForItem(dto.id)
                database.bookDao().deleteParagraphsForItem(dto.id)
            }
            // Keep an explicit selection across sha changes and newly added
            // artifacts for an Item the user already chose to download.
            val selected = previous?.downloadState?.let { it != "none" } ?: itemSelected
            if (selected) needsDownload = true
            database.artifactDao().upsert(
                ArtifactEntity(
                    itemId = dto.id,
                    kind = file.kind,
                    sha256 = file.sha256,
                    size = file.size,
                    mime = file.mime,
                    version = file.version,
                    localPath = null,
                    downloadState = if (selected) "queued" else "none",
                    downloadedBytes = 0,
                    etag = null,
                    errorCode = null,
                )
            )
        }
        for ((kind, previous) in existing) {
            if (kind in currentKinds) continue
            database.artifactDao().delete(dto.id, kind)
            if (kind == "transcript") {
                database.transcriptSegmentDao().deleteForItem(dto.id)
            }
            if (kind == "book_json") {
                database.bookDao().deleteForItem(dto.id)
                database.bookDao().deleteParagraphsForItem(dto.id)
            }
            if (previous.localPath != null) {
                filesToDelete += kind to previous.localPath
            }
        }
        return ArtifactOutcome(filesToDelete, needsDownload)
    }

    private suspend fun cleanupRemovedArtifacts(
        itemId: String,
        files: List<Pair<String, String?>>,
    ) {
        if (files.isEmpty()) return
        val playing = nowPlayingItemId() == itemId
        val paths = files.mapNotNull { it.second }
        if (playing) {
            database.pendingDeletionDao().upsertAll(
                paths.map { PendingDeletionEntity(path = it, itemId = itemId) }
            )
        } else {
            files.forEach { (kind, path) -> fileStore.deleteArtifact(itemId, kind, path) }
        }
    }

    private suspend fun syncState(client: TroveClient) {
        val cursor = database.syncCursorDao().current()
        var stateCursor = cursor?.stateCursor
        var epoch = cursor?.epoch
        while (true) {
            if (database.pendingMutationDao().count() > 0) return
            val page = fetchState(client, stateCursor)
            if (epoch != null && page.epoch != epoch) throw FullResyncRequired()
            epoch = page.epoch
            if (database.pendingMutationDao().count() > 0) return
            applyStatePage(page)
            stateCursor = page.nextCursor
            saveCursor(stateCursor = stateCursor, epoch = epoch)
            if (!page.hasMore) break
        }
    }

    private suspend fun fetchState(client: TroveClient, cursor: String?): SyncStateDto =
        try {
            client.state(cursor = cursor, limit = pageSize)
        } catch (error: TroveApiException) {
            if (error.code == CURSOR_INVALID) throw FullResyncRequired()
            throw error
        }

    private suspend fun applyStatePage(page: SyncStateDto) {
        database.writeTransaction {
            for (item in page.items) {
                val pending = database.pendingMutationDao().fieldsForItem(item.id)
                if (blocksState(pending)) continue
                database.itemDao().applyState(
                    id = item.id,
                    positionSec = item.audioPositionSec,
                    bookLocator = item.bookLocator,
                    consumptionState = item.consumptionState,
                    lastConsumedAt = item.lastConsumedAt,
                    stateSeq = item.stateSeq,
                )
            }
        }
    }

    private suspend fun reconcileDeletedItems(seen: Set<String>) {
        val localIds = database.itemDao().allIds()
        for (id in localIds) {
            if (id !in seen) deleteItem(id, maximumVersion = null)
        }
    }

    private suspend fun deleteItem(id: String, maximumVersion: Int?) {
        val existing = database.itemDao().find(id)
        if (existing == null) {
            indexChanged(id)
            return
        }
        if (maximumVersion != null && existing.version > maximumVersion) return
        val artifacts = database.artifactDao().forItem(id)
        val playing = nowPlayingItemId() == id
        val paths = artifacts.mapNotNull { it.localPath }
        database.writeTransaction {
            database.itemDao().delete(id)
            if (playing && paths.isNotEmpty()) {
                database.pendingDeletionDao().upsertAll(
                    paths.map { PendingDeletionEntity(path = it, itemId = id) }
                )
            }
        }
        if (!playing) {
            artifacts.forEach { fileStore.deleteArtifact(id, it.kind, it.localPath) }
            fileStore.deleteItem(id)
        }
        indexChanged(id)
    }

    private suspend fun resetCursors() {
        val current = database.syncCursorDao().current()
        database.syncCursorDao().upsert(
            SyncCursorEntity(
                contentCursor = null,
                stateCursor = null,
                epoch = null,
                lastSuccessAt = current?.lastSuccessAt,
                errorCode = current?.errorCode,
            )
        )
    }

    private suspend fun saveCursor(
        contentCursor: String? = null,
        stateCursor: String? = null,
        epoch: String? = null,
        lastSuccessAt: Long? = null,
        errorCode: String? = null,
    ) {
        val current = database.syncCursorDao().current()
        database.syncCursorDao().upsert(
            SyncCursorEntity(
                contentCursor = contentCursor ?: current?.contentCursor,
                stateCursor = stateCursor ?: current?.stateCursor,
                epoch = epoch ?: current?.epoch,
                lastSuccessAt = lastSuccessAt ?: current?.lastSuccessAt,
                errorCode = errorCode,
            )
        )
    }

    private suspend fun offline(previous: Long?): SyncResult {
        saveCursor(errorCode = OFFLINE_CODE)
        _status.value = SyncStatus.Offline(previous)
        return SyncResult(success = false, errorCode = OFFLINE_CODE)
    }

    private suspend fun fail(
        code: String,
        message: String,
        previous: Long?,
    ): SyncResult {
        saveCursor(errorCode = code)
        _status.value = SyncStatus.Error(code, message, previous)
        return SyncResult(success = false, errorCode = code)
    }

    private class FullResyncRequired : Exception()

    private data class ArtifactOutcome(
        val filesToDelete: List<Pair<String, String?>>,
        val needsDownload: Boolean,
    )
}
