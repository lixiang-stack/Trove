package dev.trove.app.testing

import android.content.Context
import dev.trove.app.AppContainer
import dev.trove.core.auth.StoredCredential
import dev.trove.core.auth.TokenStore
import dev.trove.core.db.TroveDatabase
import dev.trove.core.network.DeviceDto
import dev.trove.core.network.DeviceListResponse
import dev.trove.core.network.DeviceTokenResponse
import dev.trove.core.network.HealthDto
import dev.trove.core.network.ManifestDto
import dev.trove.core.network.SyncStateDto
import dev.trove.core.network.TroveApi
import dev.trove.core.network.TroveApiException
import dev.trove.core.network.TroveApiFactory
import dev.trove.core.settings.SettingsStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import retrofit2.Response

class FakeTokenStore(
    var credential: StoredCredential? = null,
) : TokenStore {
    var clearCalls = 0

    override suspend fun read(): StoredCredential? = credential

    override suspend fun save(credential: StoredCredential) {
        this.credential = credential
    }

    override suspend fun clear() {
        clearCalls += 1
        credential = null
    }
}

class FakeSettingsStore(
    initialHostUrl: String? = null,
) : SettingsStore {
    private val state = MutableStateFlow(initialHostUrl)
    var current: String? = initialHostUrl
        private set
    override val hostUrl: Flow<String?> = state

    override suspend fun saveHostUrl(url: String) {
        current = url
        state.value = url
    }

    override suspend fun clearHostUrl() {
        current = null
        state.value = null
    }
}

class FakeTroveApi : TroveApi {
    var healthResponse = HealthDto(
        apiVersion = "test",
        capabilities = mapOf("sync" to true, "device_tokens" to true, "file_download" to true),
    )
    var healthError: Throwable? = null
    var tokenResponse = DeviceTokenResponse(
        deviceId = "device-1",
        name = "Pixel",
        token = "test-token",
        createdAt = 1_790_000_000_000,
    )
    var tokenError: Throwable? = null
    var devicesResponse = DeviceListResponse(
        devices = listOf(
            DeviceDto(
                deviceId = "device-1",
                name = "Pixel",
                createdAt = 1_790_000_000_000,
                lastUsedAt = 1_790_000_000_000,
            )
        )
    )
    var deviceError: Throwable? = null
    val revokedDevices = mutableListOf<String>()
    var manifestResponse = ManifestDto(
        items = emptyList(),
        tombstones = emptyList(),
        nextCursor = "0",
        hasMore = false,
        epoch = "test-epoch",
    )
    var stateResponse = SyncStateDto(
        items = emptyList(),
        nextCursor = "0",
        hasMore = false,
        epoch = "test-epoch",
    )

    override suspend fun health(): HealthDto {
        healthError?.let { throw it }
        return healthResponse
    }

    override suspend fun deviceToken(request: dev.trove.core.network.DeviceTokenRequest): DeviceTokenResponse {
        tokenError?.let { throw it }
        tokenResponse = tokenResponse.copy(name = request.name)
        return tokenResponse
    }

    override suspend fun devices(): DeviceListResponse {
        deviceError?.let { throw it }
        return devicesResponse
    }

    override suspend fun revokeDevice(deviceId: String): Response<Unit> {
        deviceError?.let { throw it }
        revokedDevices += deviceId
        return Response.success(Unit)
    }

    override suspend fun manifest(cursor: String?, limit: Int): ManifestDto = manifestResponse

    override suspend fun state(cursor: String?, limit: Int): SyncStateDto = stateResponse
}

class FakeTroveApiFactory(private val api: TroveApi) : TroveApiFactory {
    val requests = mutableListOf<Pair<String, String?>>()

    override fun create(baseUrl: String, token: String?): TroveApi {
        requests += baseUrl to token
        return api
    }
}

class TestAppContainer(
    context: Context,
    val api: FakeTroveApi = FakeTroveApi(),
    tokenStore: FakeTokenStore = FakeTokenStore(),
    settingsStore: FakeSettingsStore = FakeSettingsStore(),
    apiFactory: FakeTroveApiFactory = FakeTroveApiFactory(api),
    allowDebugCleartext: Boolean = false,
) : AppContainer(
    context = context,
    tokenStore = tokenStore,
    settingsStore = settingsStore,
    apiFactory = apiFactory,
    database = TroveDatabase.inMemory(context),
    allowDebugCleartext = allowDebugCleartext,
)

data class TestHarness(
    val container: TestAppContainer,
) {
    val api: FakeTroveApi get() = container.api
    val apiFactory: FakeTroveApiFactory get() = container.apiFactory as FakeTroveApiFactory
    val tokenStore: FakeTokenStore get() = container.tokenStore as FakeTokenStore
    val settingsStore: FakeSettingsStore get() = container.settingsStore as FakeSettingsStore
}

fun testHarness(
    context: Context,
    tokenStore: FakeTokenStore = FakeTokenStore(),
    settingsStore: FakeSettingsStore = FakeSettingsStore(),
    api: FakeTroveApi = FakeTroveApi(),
    allowDebugCleartext: Boolean = false,
): TestHarness = TestHarness(
    TestAppContainer(
        context = context,
        api = api,
        tokenStore = tokenStore,
        settingsStore = settingsStore,
        allowDebugCleartext = allowDebugCleartext,
    )
)

fun unauthorized(): TroveApiException = TroveApiException(
    code = "auth.device_revoked",
    message = "Device authorization has been revoked",
    statusCode = 401,
)
