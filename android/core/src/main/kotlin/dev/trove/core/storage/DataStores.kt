package dev.trove.core.storage

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStore

val Context.settingsDataStore: DataStore<Preferences> by preferencesDataStore(
    name = "trove_settings"
)

val Context.tokenDataStore: DataStore<Preferences> by preferencesDataStore(
    name = "trove_token"
)
