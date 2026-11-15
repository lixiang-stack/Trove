package dev.trove.core.download

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

const val DEFAULT_QUOTA_BYTES = 5L * 1024 * 1024 * 1024

data class DownloadPreferences(
    val allowMetered: Boolean = false,
    val chargingOnly: Boolean = false,
    val quotaBytes: Long = DEFAULT_QUOTA_BYTES,
)

interface DownloadSettingsStore {
    val preferences: Flow<DownloadPreferences>

    suspend fun setAllowMetered(value: Boolean)

    suspend fun setChargingOnly(value: Boolean)

    suspend fun setQuotaBytes(value: Long)
}

private val Context.downloadDataStore: DataStore<Preferences> by preferencesDataStore(
    name = "trove_downloads"
)

private val ALLOW_METERED = booleanPreferencesKey("allow_metered")
private val CHARGING_ONLY = booleanPreferencesKey("charging_only")
private val QUOTA_BYTES = longPreferencesKey("quota_bytes")

class DataStoreDownloadSettingsStore(context: Context) : DownloadSettingsStore {
    private val dataStore = context.downloadDataStore

    override val preferences: Flow<DownloadPreferences> = dataStore.data.map { values ->
        DownloadPreferences(
            allowMetered = values[ALLOW_METERED] ?: false,
            chargingOnly = values[CHARGING_ONLY] ?: false,
            quotaBytes = values[QUOTA_BYTES] ?: DEFAULT_QUOTA_BYTES,
        )
    }

    override suspend fun setAllowMetered(value: Boolean) {
        dataStore.edit { it[ALLOW_METERED] = value }
    }

    override suspend fun setChargingOnly(value: Boolean) {
        dataStore.edit { it[CHARGING_ONLY] = value }
    }

    override suspend fun setQuotaBytes(value: Long) {
        dataStore.edit { it[QUOTA_BYTES] = value }
    }
}
