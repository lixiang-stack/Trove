package dev.trove.core.network

import java.io.IOException
import javax.net.ssl.SSLException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import retrofit2.HttpException
import retrofit2.Response

class TroveApiException(
    val code: String,
    override val message: String,
    val statusCode: Int,
    val details: JsonElement? = null,
    val retryAfterSeconds: Long? = null,
) : Exception(message)

class TroveNetworkException(
    override val message: String,
    cause: Throwable? = null,
) : Exception(message, cause)

class TroveTlsException(
    override val message: String,
    cause: Throwable? = null,
) : Exception(message, cause)

fun interface UnauthorizedListener {
    fun onUnauthorized(code: String)
}

class TroveClient(
    private val api: TroveApi,
    private val unauthorizedListener: UnauthorizedListener = UnauthorizedListener {},
) {
    private val json = Json { ignoreUnknownKeys = true }

    suspend fun health(): HealthDto = call { api.health() }

    suspend fun deviceToken(password: String, name: String): DeviceTokenResponse =
        call { api.deviceToken(DeviceTokenRequest(password = password, name = name)) }

    suspend fun devices(): DeviceListResponse = call { api.devices() }

    suspend fun revokeDevice(deviceId: String) {
        val response = call { api.revokeDevice(deviceId) }
        throwIfUnsuccessful(response)
    }

    suspend fun manifest(cursor: String? = null, limit: Int = 100): ManifestDto =
        call { api.manifest(cursor, limit) }

    suspend fun state(cursor: String? = null, limit: Int = 100): SyncStateDto =
        call { api.state(cursor, limit) }

    suspend fun progress(
        itemId: String,
        request: ProgressRequestDto,
        idempotencyKey: String?,
    ): MutationResponseDto =
        call { api.progress(itemId, request, idempotencyKey) }

    suspend fun tags(
        itemId: String,
        request: TagsRequestDto,
        idempotencyKey: String?,
    ): MutationResponseDto =
        call { api.tags(itemId, request, idempotencyKey) }

    suspend fun createItem(request: ItemCreateRequestDto): ItemCreateResponseDto =
        call { api.createItem(request) }

    suspend fun item(itemId: String): ItemDto = call { api.item(itemId) }

    suspend fun retryItem(itemId: String): ItemDto = call { api.retryItem(itemId) }

    suspend fun previewFeed(url: String): FeedPreviewResponseDto =
        call { api.previewFeed(FeedPreviewRequestDto(url)) }

    suspend fun search(
        query: String,
        type: String? = null,
        consumption: String? = null,
        tag: String? = null,
        source: String? = null,
        limit: Int = 50,
    ): SearchResponseDto = call {
        api.search(query, type, consumption, tag, source, limit)
    }

    suspend fun deleteItem(itemId: String) {
        val response = call { api.deleteItem(itemId) }
        throwIfUnsuccessful(response)
    }

    private fun throwIfUnsuccessful(response: Response<Unit>) {
        if (response.isSuccessful) return
        val parsed = response.errorBody()?.string()?.let {
            runCatching { json.decodeFromString<ApiErrorBody>(it) }.getOrNull()
        }
        val code = parsed?.code?.takeIf { it.isNotBlank() } ?: "http.${response.code()}"
        if (response.code() == 401) {
            unauthorizedListener.onUnauthorized(code)
        }
        throw TroveApiException(
            code = code,
            message = parsed?.message?.takeIf { it.isNotBlank() } ?: "Request failed",
            statusCode = response.code(),
            details = parsed?.details,
        )
    }

    private suspend fun <T> call(block: suspend () -> T): T {
        try {
            return block()
        } catch (error: HttpException) {
            val body = runCatching {
                error.response()?.errorBody()?.string()
            }.getOrNull()
            val parsed = body
                ?.let { runCatching { json.decodeFromString<ApiErrorBody>(it) }.getOrNull() }
            val code = parsed?.code?.takeIf { it.isNotBlank() } ?: "http.${error.code()}"
            val message = parsed?.message?.takeIf { it.isNotBlank() } ?: "Request failed"
            if (error.code() == 401) {
                unauthorizedListener.onUnauthorized(code)
            }
            throw TroveApiException(
                code = code,
                message = message,
                statusCode = error.code(),
                details = parsed?.details,
                retryAfterSeconds = error.response()
                    ?.headers()
                    ?.get("Retry-After")
                    ?.toLongOrNull(),
            )
        } catch (error: IOException) {
            if (error.hasTlsCause()) {
                throw TroveTlsException("TLS handshake failed", error)
            }
            throw TroveNetworkException("Host is unreachable", error)
        }
    }
}

private fun Throwable.hasTlsCause(): Boolean {
    var current: Throwable? = this
    while (current != null) {
        if (current is SSLException) {
            return true
        }
        current = current.cause
    }
    return false
}
