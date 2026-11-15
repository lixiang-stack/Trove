package dev.trove.app

import android.content.Context
import dev.trove.app.session.SessionController
import dev.trove.core.auth.KeystoreTokenStore
import dev.trove.core.auth.TokenStore
import dev.trove.core.db.TroveDatabase
import dev.trove.core.network.RetrofitTroveApiFactory
import dev.trove.core.network.TroveApiFactory
import dev.trove.core.settings.DataStoreSettingsStore
import dev.trove.core.settings.SettingsStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

open class AppContainer(
    context: Context,
    val tokenStore: TokenStore = KeystoreTokenStore(context),
    val settingsStore: SettingsStore = DataStoreSettingsStore(context),
    val apiFactory: TroveApiFactory = RetrofitTroveApiFactory(),
    database: TroveDatabase? = null,
    allowDebugCleartext: Boolean = BuildConfig.DEBUG,
) {
    val database: TroveDatabase = database ?: TroveDatabase.create(context)

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val sessionController: SessionController = SessionController(
        tokenStore = tokenStore,
        settingsStore = settingsStore,
        apiFactory = apiFactory,
        allowDebugCleartext = allowDebugCleartext,
        scope = scope,
    )
}
