package dev.trove.core.download

import dev.trove.core.db.ArtifactEntity
import dev.trove.core.db.PendingDeletionEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.db.writeTransaction
import dev.trove.core.network.TroveHttpClients
import dev.trove.core.storage.ArtifactFileStore
import dev.trove.core.sync.DownloadQueue
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request

const val QUOTA_EXCEEDED = "download.quota_exceeded"
const val NO_SPACE = "download.no_space"
const val SHA_MISMATCH = "download.sha256_mismatch"
const val SIZE_MISMATCH = "download.size_mismatch"
const val HTTP_ERROR = "download.http_error"
const val NETWORK_ERROR = "download.network"
const val ITEM_MISSING = "download.item_missing"
const val NO_ARTIFACTS = "download.no_artifacts"
const val CANCELLED = "download.cancelled"

class DownloadException(
    val code: String,
    override val message: String,
    val retriable: Boolean,
    cause: Throwable? = null,
) : Exception(message, cause)

class ArtifactDownloader(
    private val database: TroveDatabase,
    private val fileStore: ArtifactFileStore,
    private val hostProvider: suspend () -> String?,
    private val tokenProvider: suspend () -> String?,
    private val preferencesProvider: suspend () -> DownloadPreferences = { DownloadPreferences() },
    private val clientFactory: (String?) -> OkHttpClient = { TroveHttpClients.create(it, 60) },
    private val onUnauthorized: (String) -> Unit = {},
    private val nowPlayingItemId: () -> String? = { null },
    private val onItemFilesChanged: suspend (String) -> Unit = {},
) {
    suspend fun downloadItem(itemId: String, onProgress: (Float) -> Unit = {}): Int {
        val artifacts = database.artifactDao().forItem(itemId)
        if (artifacts.isEmpty()) {
            throw DownloadException(NO_ARTIFACTS, "Item has no downloadable files", retriable = false)
        }
        val host = hostProvider()
            ?: throw DownloadException(NETWORK_ERROR, "Host is not configured", retriable = true)
        val token = tokenProvider()
        checkQuota(itemId, artifacts)
        val client = clientFactory(token)
        var completed = 0
        artifacts.forEachIndexed { index, artifact ->
            if (database.itemDao().find(itemId) == null) {
                throw DownloadException(ITEM_MISSING, "Item was deleted", retriable = false)
            }
            val current = database.artifactDao().find(itemId, artifact.kind)
                ?: return@forEachIndexed
            if (current.downloadState == "paused" || current.downloadState == "none") {
                return@forEachIndexed
            }
            if (current.downloadState == "completed" && localFile(itemId, current) != null) {
                completed += 1
                onProgress((index + 1f) / artifacts.size)
                return@forEachIndexed
            }
            downloadArtifact(client, host, itemId, current, onProgress)
            completed += 1
        }
        onItemFilesChanged(itemId)
        return completed
    }

    suspend fun markPaused(itemId: String) {
        database.artifactDao().forItem(itemId)
            .filter { it.downloadState == "queued" || it.downloadState == "downloading" }
            .forEach {
                database.artifactDao().setDownloadState(itemId, it.kind, "paused", null)
            }
    }

    suspend fun removeDownload(itemId: String) {
        val artifacts = database.artifactDao().forItem(itemId)
        val playing = nowPlayingItemId() == itemId
        database.writeTransaction {
            for (artifact in artifacts) {
                database.artifactDao().upsert(
                    artifact.copy(
                        localPath = null,
                        downloadState = "none",
                        downloadedBytes = 0,
                        etag = null,
                        errorCode = null,
                    )
                )
            }
            database.transcriptSegmentDao().deleteForItem(itemId)
            database.bookDao().deleteForItem(itemId)
            database.bookDao().deleteParagraphsForItem(itemId)
        }
        artifacts.forEach { artifact ->
            if (playing && artifact.kind == "audio" && artifact.localPath != null) {
                database.pendingDeletionDao().upsertAll(
                    listOf(PendingDeletionEntity(path = artifact.localPath, itemId = itemId))
                )
            } else {
                fileStore.deleteArtifact(itemId, artifact.kind, artifact.localPath)
            }
        }
        onItemFilesChanged(itemId)
    }

    private suspend fun downloadArtifact(
        client: OkHttpClient,
        host: String,
        itemId: String,
        artifact: ArtifactEntity,
        onProgress: (Float) -> Unit,
    ) {
        val target = fileStore.pathFor(itemId, artifact.kind, artifact.mime)
        val part = fileStore.partFor(target)
        database.artifactDao().setDownloadState(itemId, artifact.kind, "downloading", null)
        try {
            val etag = fetchToPart(client, host, itemId, artifact, target, part, onProgress)
            val current = database.artifactDao().find(itemId, artifact.kind)
            if (current == null || current.downloadState == "none") {
                part.delete()
                throw DownloadException(CANCELLED, "Download was cancelled", retriable = false)
            }
            if (current.downloadState == "paused") {
                throw DownloadException(CANCELLED, "Download was paused", retriable = false)
            }
            verifyAndInstall(itemId, artifact, target, part, etag)
        } catch (error: DownloadException) {
            if (error.code == CANCELLED) {
                val current = database.artifactDao().find(itemId, artifact.kind)
                if (current == null || current.downloadState == "none") {
                    part.delete()
                }
            } else {
                database.artifactDao().updateProgress(
                    itemId = itemId,
                    kind = artifact.kind,
                    state = "failed",
                    downloadedBytes = if (part.isFile) part.length() else 0,
                    etag = artifact.etag,
                    errorCode = error.code,
                )
            }
            throw error
        } catch (error: IOException) {
            database.artifactDao().updateProgress(
                itemId = itemId,
                kind = artifact.kind,
                state = "failed",
                downloadedBytes = if (part.isFile) part.length() else 0,
                etag = artifact.etag,
                errorCode = NETWORK_ERROR,
            )
            throw DownloadException(NETWORK_ERROR, "Download interrupted", true, error)
        }
    }

    private suspend fun fetchToPart(
        client: OkHttpClient,
        host: String,
        itemId: String,
        artifact: ArtifactEntity,
        target: File,
        part: File,
        onProgress: (Float) -> Unit,
        allowRestart: Boolean = true,
    ): String? {
        val storedPart = part.takeIf { it.isFile && it.length() > 0 }
        val storedEtag = artifact.etag
        val resume = storedPart != null && storedEtag != null
        val request = Request.Builder()
            .url(urlFor(host, itemId, artifact.kind))
            .apply {
                if (resume) {
                    header("Range", "bytes=${storedPart.length()}-")
                    header("If-Range", storedEtag)
                }
            }
            .build()
        client.newCall(request).execute().use { response ->
            if (response.code == 416 && resume) {
                if (!allowRestart) {
                    throw DownloadException(HTTP_ERROR, "Range request rejected", retriable = true)
                }
                part.delete()
                return fetchToPart(
                    client, host, itemId, artifact, target, part, onProgress, allowRestart = false
                )
            }
            if (!response.isSuccessful) {
                if (response.code == 401) {
                    onUnauthorized("auth.device_token_invalid")
                }
                val retriable = response.code == 429 || response.code >= 500
                throw DownloadException(
                    HTTP_ERROR,
                    "File download failed with HTTP ${response.code}",
                    retriable,
                )
            }
            val responseEtag = response.header("ETag")
            val appending = response.code == 206 && resume
            if (appending && responseEtag != null && responseEtag != storedEtag) {
                if (!allowRestart) {
                    throw DownloadException(HTTP_ERROR, "ETag changed during resume", retriable = true)
                }
                part.delete()
                return fetchToPart(
                    client, host, itemId, artifact, target, part, onProgress, allowRestart = false
                )
            }
            if (!appending) {
                part.delete()
            }
            val startBytes = if (appending) part.length() else 0L
            writeBody(
                body = response.body.byteStream(),
                part = part,
                append = appending,
                startBytes = startBytes,
                artifact = artifact,
                itemId = itemId,
                etag = responseEtag,
                onProgress = onProgress,
            )
            return responseEtag
        }
    }

    private suspend fun writeBody(
        body: java.io.InputStream,
        part: File,
        append: Boolean,
        startBytes: Long,
        artifact: ArtifactEntity,
        itemId: String,
        etag: String?,
        onProgress: (Float) -> Unit,
    ) {
        var written = startBytes
        var lastReported = written
        val output = if (append) {
            java.io.FileOutputStream(part, true)
        } else {
            java.io.FileOutputStream(part, false)
        }
        body.use { input ->
            output.use { stream ->
                val buffer = ByteArray(BUFFER_SIZE)
                while (true) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    stream.write(buffer, 0, read)
                    written += read
                    if (written - lastReported >= PROGRESS_STEP_BYTES) {
                        lastReported = written
                        reportProgress(itemId, artifact, written, etag, onProgress)
                    }
                }
            }
        }
        reportProgress(itemId, artifact, written, etag, onProgress)
    }

    private suspend fun reportProgress(
        itemId: String,
        artifact: ArtifactEntity,
        written: Long,
        etag: String?,
        onProgress: (Float) -> Unit,
    ) {
        val current = database.artifactDao().find(itemId, artifact.kind)
        if (current == null || current.downloadState == "none" || current.downloadState == "paused") {
            throw DownloadException(CANCELLED, "Download was cancelled", retriable = false)
        }
        database.artifactDao().updateProgress(
            itemId = itemId,
            kind = artifact.kind,
            state = "downloading",
            downloadedBytes = written,
            etag = etag,
            errorCode = null,
        )
        onProgress((written.toFloat() / artifact.size.coerceAtLeast(1)).coerceIn(0f, 1f))
    }

    private suspend fun verifyAndInstall(
        itemId: String,
        artifact: ArtifactEntity,
        target: File,
        part: File,
        etag: String?,
    ) {
        if (artifact.size > 0 && part.length() != artifact.size) {
            part.delete()
            throw DownloadException(SIZE_MISMATCH, "Downloaded size does not match manifest", true)
        }
        val digest = sha256(part)
        if (digest != artifact.sha256) {
            part.delete()
            throw DownloadException(SHA_MISMATCH, "Downloaded file failed checksum", true)
        }
        target.delete()
        moveAtomically(part, target)
        database.pendingDeletionDao().deletePaths(listOf(target.absolutePath))
        database.artifactDao().upsert(
            artifact.copy(
                localPath = target.absolutePath,
                downloadState = "completed",
                downloadedBytes = target.length(),
                etag = etag,
                errorCode = null,
            )
        )
    }

    private suspend fun checkQuota(itemId: String, artifacts: List<ArtifactEntity>) {
        val preferences = preferencesProvider()
        val remaining = artifacts.sumOf {
            if (it.downloadState == "completed" && localFile(itemId, it) != null) 0 else it.size
        }
        val used = database.artifactDao().completedBytes()
        if (used + remaining > preferences.quotaBytes) {
            throw DownloadException(QUOTA_EXCEEDED, "Download quota exceeded", retriable = false)
        }
        if (fileStore.usableSpace() < remaining + SPACE_MARGIN_BYTES) {
            throw DownloadException(NO_SPACE, "Not enough storage space", retriable = false)
        }
    }

    private fun localFile(itemId: String, artifact: ArtifactEntity): File? =
        fileStore.existingFile(itemId, artifact.kind, artifact.localPath)

    private fun urlFor(host: String, itemId: String, kind: String): String {
        val base = host.trimEnd('/').toHttpUrl()
        return base.newBuilder()
            .addPathSegment("api")
            .addPathSegment("items")
            .addPathSegment(itemId)
            .addPathSegment("files")
            .addPathSegment(kind)
            .build()
            .toString()
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(BUFFER_SIZE)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun moveAtomically(source: File, target: File) {
        try {
            Files.move(
                source.toPath(),
                target.toPath(),
                StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE,
            )
        } catch (_: IOException) {
            Files.move(source.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING)
        }
    }

    private companion object {
        const val BUFFER_SIZE = 64 * 1024
        const val PROGRESS_STEP_BYTES = 512L * 1024
        const val SPACE_MARGIN_BYTES = 32L * 1024 * 1024
    }
}

interface DownloadManager {
    suspend fun enqueue(itemId: String)

    suspend fun pause(itemId: String)

    suspend fun retry(itemId: String)

    suspend fun remove(itemId: String)
}

class DefaultDownloadManager(
    private val database: TroveDatabase,
    private val downloader: ArtifactDownloader,
    private val queue: DownloadQueue,
) : DownloadManager {
    override suspend fun enqueue(itemId: String) {
        markQueued(itemId)
        queue.enqueue(itemId)
    }

    override suspend fun pause(itemId: String) {
        downloader.markPaused(itemId)
    }

    override suspend fun retry(itemId: String) {
        markQueued(itemId)
        queue.enqueue(itemId)
    }

    override suspend fun remove(itemId: String) {
        downloader.removeDownload(itemId)
    }

    private suspend fun markQueued(itemId: String) {
        database.artifactDao().forItem(itemId)
            .filter { it.downloadState != "completed" }
            .forEach {
                database.artifactDao().setDownloadState(itemId, it.kind, "queued", null)
            }
    }
}
