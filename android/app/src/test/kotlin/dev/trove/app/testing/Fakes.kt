package dev.trove.app.testing

import android.content.Context
import dev.trove.app.AppContainer
import dev.trove.core.auth.StoredCredential
import dev.trove.core.auth.TokenStore
import dev.trove.core.db.TroveDatabase
import dev.trove.core.download.DownloadManager
import dev.trove.core.download.DownloadPreferences
import dev.trove.core.download.DownloadSettingsStore
import dev.trove.core.network.DeviceDto
import dev.trove.core.network.DeviceListResponse
import dev.trove.core.network.DeviceTokenResponse
import dev.trove.core.network.FeedPreviewRequestDto
import dev.trove.core.network.FeedPreviewResponseDto
import dev.trove.core.network.HealthDto
import dev.trove.core.network.ItemCreateRequestDto
import dev.trove.core.network.ItemCreateResponseDto
import dev.trove.core.network.ItemDto
import dev.trove.core.network.ManifestDto
import dev.trove.core.network.MutationItemDto
import dev.trove.core.network.MutationResponseDto
import dev.trove.core.network.ProgressRequestDto
import dev.trove.core.network.SearchResponseDto
import dev.trove.core.network.SyncItemDto
import dev.trove.core.network.SyncStateDto
import dev.trove.core.network.TagsRequestDto
import dev.trove.core.network.TroveApi
import dev.trove.core.network.TroveApiException
import dev.trove.core.network.TroveApiFactory
import dev.trove.core.settings.SettingsStore
import dev.trove.core.settings.SyncPreferences
import dev.trove.core.sync.DownloadQueue
import dev.trove.playback.PlaybackRequest
import dev.trove.playback.PlaybackState
import dev.trove.playback.PlayerGateway
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
    private val sync = MutableStateFlow(SyncPreferences())
    var current: String? = initialHostUrl
        private set
    override val hostUrl: Flow<String?> = state
    override val syncPreferences: Flow<SyncPreferences> = sync

    override suspend fun saveHostUrl(url: String) {
        current = url
        state.value = url
    }

    override suspend fun clearHostUrl() {
        current = null
        state.value = null
    }

    override suspend fun setPeriodicSyncEnabled(value: Boolean) {
        sync.value = sync.value.copy(periodicEnabled = value)
    }

    override suspend fun setSyncIntervalMinutes(value: Long) {
        sync.value = sync.value.copy(intervalMinutes = value)
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
    var manifestError: Throwable? = null
    var stateError: Throwable? = null
    var progressError: Throwable? = null
    val progressCalls = mutableListOf<Pair<String, ProgressRequestDto>>()
    var deleteError: Throwable? = null
    val deletedItems = mutableListOf<String>()
    val tagCalls = mutableListOf<Pair<String, List<String>>>()
    var tagsError: Throwable? = null
    var createResponse: ItemCreateResponseDto? = null
    var createError: Throwable? = null
    val createCalls = mutableListOf<ItemCreateRequestDto>()
    var itemResponse: ItemDto? = null
    var itemError: Throwable? = null
    var feedResponse: FeedPreviewResponseDto = FeedPreviewResponseDto(title = "Feed")
    var feedError: Throwable? = null
    var searchResponse: SearchResponseDto? = null
    var searchError: Throwable? = null

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

    override suspend fun manifest(cursor: String?, limit: Int): ManifestDto {
        manifestError?.let { throw it }
        return manifestResponse
    }

    override suspend fun state(cursor: String?, limit: Int): SyncStateDto {
        stateError?.let { throw it }
        return stateResponse
    }

    override suspend fun progress(
        itemId: String,
        body: ProgressRequestDto,
        idempotencyKey: String?,
    ): MutationResponseDto {
        progressError?.let { throw it }
        progressCalls += itemId to body
        return MutationResponseDto(
            item = dev.trove.core.network.MutationItemDto(
                id = itemId,
                audioPositionSec = body.positionSec ?: 0.0,
                consumptionState = body.consumptionState ?: "unstarted",
            )
        )
    }

    override suspend fun deleteItem(itemId: String): Response<Unit> {
        deleteError?.let { throw it }
        deletedItems += itemId
        return Response.success(Unit)
    }

    override suspend fun tags(
        itemId: String,
        body: TagsRequestDto,
        idempotencyKey: String?,
    ): MutationResponseDto {
        tagsError?.let { throw it }
        tagCalls += itemId to body.tags
        return MutationResponseDto(
            item = MutationItemDto(
                id = itemId,
                tags = body.tags,
            )
        )
    }

    override suspend fun createItem(body: ItemCreateRequestDto): ItemCreateResponseDto {
        createError?.let { throw it }
        createCalls += body
        return createResponse ?: ItemCreateResponseDto(
            item = ItemDto(
                id = "created-item",
                title = body.url ?: body.feedUrl.orEmpty(),
                processingState = "queued",
            )
        )
    }

    override suspend fun item(itemId: String): ItemDto {
        itemError?.let { throw it }
        return itemResponse ?: ItemDto(id = itemId, title = "Item", processingState = "queued")
    }

    override suspend fun retryItem(itemId: String): ItemDto {
        itemError?.let { throw it }
        return itemResponse ?: ItemDto(id = itemId, title = "Item", processingState = "queued")
    }

    override suspend fun previewFeed(body: FeedPreviewRequestDto): FeedPreviewResponseDto {
        feedError?.let { throw it }
        return feedResponse
    }

    override suspend fun search(
        query: String,
        type: String?,
        consumption: String?,
        tag: String?,
        source: String?,
        limit: Int,
    ): SearchResponseDto {
        searchError?.let { throw it }
        searchResponse?.let { return it }
        val matches = manifestResponse.items.filter { item ->
            listOfNotNull(item.title, item.summary, item.author).any {
                it.contains(query, ignoreCase = true)
            } || item.tags.any { it.contains(query, ignoreCase = true) }
        }
        return SearchResponseDto(
            query = query,
            results = matches.map { item ->
                dev.trove.core.network.SearchResultDto(
                    item = item.toItemDto(),
                    evidence = emptyList(),
                )
            },
            count = matches.size,
        )
    }
}

private fun SyncItemDto.toItemDto(): ItemDto = ItemDto(
    id = id,
    version = version,
    sourceType = sourceType,
    platform = platform,
    title = title,
    author = author,
    publishedAt = publishedAt,
    fetchedAt = fetchedAt,
    language = language,
    durationSec = durationSec,
    summary = summary,
    tags = tags,
    processingState = processingState,
    errorCode = errorCode,
    errorMessage = errorMessage,
    hasAudio = hasAudio,
    hasBook = hasBook,
)

class FakeDownloadSettingsStore(
    initial: DownloadPreferences = DownloadPreferences(),
) : DownloadSettingsStore {
    private val state = MutableStateFlow(initial)
    override val preferences: Flow<DownloadPreferences> = state

    override suspend fun setAllowMetered(value: Boolean) {
        state.value = state.value.copy(allowMetered = value)
    }

    override suspend fun setChargingOnly(value: Boolean) {
        state.value = state.value.copy(chargingOnly = value)
    }

    override suspend fun setQuotaBytes(value: Long) {
        state.value = state.value.copy(quotaBytes = value)
    }
}

class FakeDownloadQueue : DownloadQueue {
    val enqueued = mutableListOf<String>()

    override suspend fun enqueue(itemId: String) {
        enqueued += itemId
    }
}

class FakeDownloadManager : DownloadManager {
    val enqueued = mutableListOf<String>()
    val paused = mutableListOf<String>()
    val retried = mutableListOf<String>()
    val removed = mutableListOf<String>()

    override suspend fun enqueue(itemId: String) {
        enqueued += itemId
    }

    override suspend fun pause(itemId: String) {
        paused += itemId
    }

    override suspend fun retry(itemId: String) {
        retried += itemId
    }

    override suspend fun remove(itemId: String) {
        removed += itemId
    }
}

class FakePlayer : PlayerGateway {
    private val playback = MutableStateFlow(PlaybackState(connected = true))
    override val state: kotlinx.coroutines.flow.StateFlow<PlaybackState> = playback
    val requests = mutableListOf<PlaybackRequest>()
    var connected = false
    var errorOnPlay: String? = null
    val speeds = mutableListOf<Float>()

    override fun connect() {
        connected = true
    }

    override fun release() {
        connected = false
        playback.value = PlaybackState()
    }

    override fun play(request: PlaybackRequest) {
        requests += request
        playback.value = playback.value.copy(
            itemId = request.itemId,
            title = request.title,
            artist = request.artist,
            artworkUrl = request.artworkUrl,
            isPlaying = true,
            positionMs = request.startPositionMs,
            errorCode = errorOnPlay,
        )
    }

    override fun pause() {
        playback.value = playback.value.copy(isPlaying = false)
    }

    override fun toggle() {
        playback.value = playback.value.copy(isPlaying = !playback.value.isPlaying)
    }

    override fun seekTo(positionMs: Long) {
        playback.value = playback.value.copy(positionMs = positionMs)
    }

    override fun setSpeed(speed: Float) {
        speeds += speed
        playback.value = playback.value.copy(speed = speed)
    }
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
    val fakePlayer: FakePlayer = FakePlayer(),
    val fakeDownloadQueue: FakeDownloadQueue = FakeDownloadQueue(),
    val fakeDownloadSettings: FakeDownloadSettingsStore = FakeDownloadSettingsStore(),
) : AppContainer(
    context = context,
    tokenStore = tokenStore,
    settingsStore = settingsStore,
    apiFactory = apiFactory,
    databaseOverride = TroveDatabase.inMemory(context),
    downloadSettingsStore = fakeDownloadSettings,
    downloadQueue = fakeDownloadQueue,
    player = fakePlayer,
    allowDebugCleartext = allowDebugCleartext,
)

data class TestHarness(
    val container: TestAppContainer,
) {
    val api: FakeTroveApi get() = container.api
    val apiFactory: FakeTroveApiFactory get() = container.apiFactory as FakeTroveApiFactory
    val tokenStore: FakeTokenStore get() = container.tokenStore as FakeTokenStore
    val settingsStore: FakeSettingsStore get() = container.settingsStore as FakeSettingsStore
    val player: FakePlayer get() = container.fakePlayer
    val downloadQueue: FakeDownloadQueue get() = container.fakeDownloadQueue
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
