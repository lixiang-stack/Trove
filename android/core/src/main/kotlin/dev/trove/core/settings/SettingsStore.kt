package dev.trove.core.settings

import kotlinx.coroutines.flow.Flow

data class SyncPreferences(
    val periodicEnabled: Boolean = true,
    val intervalMinutes: Long = DEFAULT_SYNC_INTERVAL_MINUTES,
)

const val DEFAULT_SYNC_INTERVAL_MINUTES = 15L
const val MIN_SYNC_INTERVAL_MINUTES = 15L

interface SettingsStore {
    val hostUrl: Flow<String?>

    val syncPreferences: Flow<SyncPreferences>

    suspend fun saveHostUrl(url: String)

    suspend fun clearHostUrl()

    suspend fun setPeriodicSyncEnabled(value: Boolean)

    suspend fun setSyncIntervalMinutes(value: Long)
}
