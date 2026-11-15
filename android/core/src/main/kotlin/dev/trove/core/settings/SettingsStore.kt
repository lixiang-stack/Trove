package dev.trove.core.settings

import kotlinx.coroutines.flow.Flow

interface SettingsStore {
    val hostUrl: Flow<String?>

    suspend fun saveHostUrl(url: String)

    suspend fun clearHostUrl()
}
