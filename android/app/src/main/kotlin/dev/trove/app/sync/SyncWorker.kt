package dev.trove.app.sync

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import dev.trove.app.TroveApplication
import dev.trove.core.settings.MIN_SYNC_INTERVAL_MINUTES
import dev.trove.core.settings.SyncPreferences
import java.util.concurrent.TimeUnit

class SyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        val application = applicationContext as? TroveApplication ?: return Result.failure()
        val result = application.container.syncEngine.sync()
        return when (result.errorCode) {
            null -> Result.success()
            "sync.offline" -> Result.retry()
            "auth.required", "auth.device_revoked", "auth.device_token_invalid" -> Result.failure()
            else -> Result.retry()
        }
    }
}

class PeriodicSyncScheduler(private val context: Context) {
    fun apply(preferences: SyncPreferences) {
        runCatching {
            val workManager = WorkManager.getInstance(context.applicationContext)
            if (!preferences.periodicEnabled) {
                workManager.cancelUniqueWork(NAME)
                return
            }
            val interval = preferences.intervalMinutes.coerceAtLeast(MIN_SYNC_INTERVAL_MINUTES)
            val request = PeriodicWorkRequestBuilder<SyncWorker>(interval, TimeUnit.MINUTES)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build()
            workManager.enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.UPDATE, request)
        }
    }

    fun cancel() {
        runCatching {
            WorkManager.getInstance(context.applicationContext).cancelUniqueWork(NAME)
        }
    }

    private companion object {
        const val NAME = "trove-periodic-sync"
    }
}
