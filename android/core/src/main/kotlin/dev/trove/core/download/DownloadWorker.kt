package dev.trove.core.download

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.ForegroundInfo
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import dev.trove.core.auth.TokenStore
import dev.trove.core.db.TroveDatabase
import dev.trove.core.network.TroveHttpClients
import dev.trove.core.settings.SettingsStore
import dev.trove.core.storage.ArtifactFileStore
import dev.trove.core.sync.DownloadQueue
import kotlinx.coroutines.flow.first
import okhttp3.OkHttpClient

class DownloadEnvironment(
    val database: TroveDatabase,
    val fileStore: ArtifactFileStore,
    val settingsStore: SettingsStore,
    val downloadSettings: DownloadSettingsStore,
    val tokenStore: TokenStore,
    val clientFactory: (String?) -> OkHttpClient = { TroveHttpClients.create(it, 60) },
    val onUnauthorized: (String) -> Unit = {},
    val nowPlayingItemId: () -> String? = { null },
    val onItemFilesChanged: suspend (String) -> Unit = {},
) {
    fun downloader(): ArtifactDownloader = ArtifactDownloader(
        database = database,
        fileStore = fileStore,
        hostProvider = { settingsStore.hostUrl.first() },
        tokenProvider = { tokenStore.read()?.token },
        preferencesProvider = { downloadSettings.preferences.first() },
        clientFactory = clientFactory,
        onUnauthorized = onUnauthorized,
        nowPlayingItemId = nowPlayingItemId,
        onItemFilesChanged = onItemFilesChanged,
    )
}

object DownloadEnvironmentHolder {
    @Volatile
    var current: DownloadEnvironment? = null
}

class DownloadWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val environment = DownloadEnvironmentHolder.current ?: return Result.failure()
        runCatching { setForeground(foregroundInfo(null)) }
        val downloader = environment.downloader()
        var retry = false
        while (true) {
            val itemIds = environment.database.artifactDao().itemsWithPendingDownloads()
            if (itemIds.isEmpty()) break
            for (itemId in itemIds) {
                runCatching { setForeground(foregroundInfo(itemId)) }
                try {
                    downloader.downloadItem(itemId)
                } catch (error: DownloadException) {
                    if (error.retriable) {
                        requeue(environment, itemId)
                        retry = true
                        break
                    }
                    environment.database.artifactDao().markPendingFailed(itemId, error.code)
                }
            }
            if (retry) break
        }
        return if (retry) Result.retry() else Result.success()
    }

    private suspend fun requeue(environment: DownloadEnvironment, itemId: String) {
        environment.database.artifactDao().forItem(itemId)
            .filter { it.downloadState == "failed" }
            .forEach {
                environment.database.artifactDao().setDownloadState(itemId, it.kind, "queued", null)
            }
    }

    private fun foregroundInfo(itemId: String?): ForegroundInfo {
        val context = applicationContext
        ensureChannel(context)
        val text = if (itemId == null) "正在准备下载" else "正在下载"
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle("拾藏")
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setProgress(0, 0, true)
            .build()
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ForegroundInfo(
                NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            )
        } else {
            ForegroundInfo(NOTIFICATION_ID, notification)
        }
    }

    private fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                "下载",
                NotificationManager.IMPORTANCE_LOW,
            )
        )
    }

    private companion object {
        const val CHANNEL_ID = "trove_downloads"
        const val NOTIFICATION_ID = 4001
    }
}

class WorkManagerDownloadQueue(
    context: Context,
    private val downloadSettings: DownloadSettingsStore,
) : DownloadQueue {
    private val appContext = context.applicationContext

    override suspend fun enqueue(itemId: String) {
        val preferences = downloadSettings.preferences.first()
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(
                if (preferences.allowMetered) NetworkType.CONNECTED else NetworkType.UNMETERED
            )
            .setRequiresCharging(preferences.chargingOnly)
            .build()
        val request = OneTimeWorkRequestBuilder<DownloadWorker>()
            .setConstraints(constraints)
            .build()
        WorkManager.getInstance(appContext).enqueueUniqueWork(
            QUEUE_NAME,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

    private companion object {
        const val QUEUE_NAME = "trove-downloads"
        const val KEY_ITEM_ID = "item_id"
    }
}
