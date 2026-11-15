package dev.trove.core.network

import java.io.IOException
import javax.net.ssl.SSLException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import retrofit2.HttpException

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
        call { api.revokeDevice(deviceId) }
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

    suspend fun deleteItem(itemId: String) {
        val response = call { api.deleteItem(itemId) }
        if (!response.isSuccessful) {
            throw TroveApiException(
                code = "http.${response.code()}",
                message = response.message(),
                statusCode = response.code(),
            )
        }
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
