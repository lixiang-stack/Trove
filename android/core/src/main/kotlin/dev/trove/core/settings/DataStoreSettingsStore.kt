package dev.trove.core.settings

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import dev.trove.core.storage.settingsDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val HOST_URL_KEY = stringPreferencesKey("host_url")
private val PERIODIC_SYNC_KEY = booleanPreferencesKey("periodic_sync")
private val SYNC_INTERVAL_KEY = longPreferencesKey("sync_interval_minutes")

class DataStoreSettingsStore(context: Context) : SettingsStore {
    private val dataStore = context.settingsDataStore

    override val hostUrl: Flow<String?> = dataStore.data.map { preferences ->
        preferences[HOST_URL_KEY]
    }

    override val syncPreferences: Flow<SyncPreferences> = dataStore.data.map { preferences ->
        SyncPreferences(
            periodicEnabled = preferences[PERIODIC_SYNC_KEY] ?: true,
            intervalMinutes = (preferences[SYNC_INTERVAL_KEY] ?: DEFAULT_SYNC_INTERVAL_MINUTES)
                .coerceAtLeast(MIN_SYNC_INTERVAL_MINUTES),
        )
    }

    override suspend fun saveHostUrl(url: String) {
        dataStore.edit { preferences ->
            preferences[HOST_URL_KEY] = url
        }
    }

    override suspend fun clearHostUrl() {
        dataStore.edit { preferences ->
            preferences.remove(HOST_URL_KEY)
        }
    }

    override suspend fun setPeriodicSyncEnabled(value: Boolean) {
        dataStore.edit { it[PERIODIC_SYNC_KEY] = value }
    }

    override suspend fun setSyncIntervalMinutes(value: Long) {
        dataStore.edit { it[SYNC_INTERVAL_KEY] = value.coerceAtLeast(MIN_SYNC_INTERVAL_MINUTES) }
    }
}
