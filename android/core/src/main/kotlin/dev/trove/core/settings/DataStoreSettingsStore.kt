package dev.trove.core.settings

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import dev.trove.core.storage.settingsDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val HOST_URL_KEY = stringPreferencesKey("host_url")

class DataStoreSettingsStore(context: Context) : SettingsStore {
    private val dataStore = context.settingsDataStore

    override val hostUrl: Flow<String?> = dataStore.data.map { preferences ->
        preferences[HOST_URL_KEY]
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
}
