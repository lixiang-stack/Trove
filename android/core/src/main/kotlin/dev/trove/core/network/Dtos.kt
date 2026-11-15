package dev.trove.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class ApiErrorBody(
    val code: String = "",
    val message: String = "",
    val details: JsonElement? = null,
)

@Serializable
data class DeviceTokenRequest(
    val password: String,
    val name: String,
)

@Serializable
data class DeviceTokenResponse(
    @SerialName("device_id") val deviceId: String,
    val name: String,
    val token: String,
    @SerialName("created_at") val createdAt: Long,
)

@Serializable
data class DeviceDto(
    @SerialName("device_id") val deviceId: String,
    val name: String,
    @SerialName("created_at") val createdAt: Long,
    @SerialName("last_used_at") val lastUsedAt: Long,
    @SerialName("revoked_at") val revokedAt: Long? = null,
)

@Serializable
data class DeviceListResponse(
    val devices: List<DeviceDto> = emptyList(),
)

@Serializable
data class HealthDto(
    @SerialName("api_version") val apiVersion: String = "",
    val capabilities: Map<String, Boolean> = emptyMap(),
)

@Serializable
data class SyncFileDto(
    val kind: String,
    val sha256: String,
    val size: Long,
    val mime: String,
    val version: Int,
    val url: String,
)

@Serializable
data class SyncItemDto(
    val id: String,
    val version: Int,
    @SerialName("source_type") val sourceType: String,
    val platform: String,
    val title: String,
    val author: String? = null,
    @SerialName("published_at") val publishedAt: String? = null,
    @SerialName("fetched_at") val fetchedAt: Long,
    val language: String? = null,
    @SerialName("duration_sec") val durationSec: Double? = null,
    val summary: String? = null,
    val tags: List<String> = emptyList(),
    @SerialName("processing_state") val processingState: String,
    @SerialName("error_code") val errorCode: String? = null,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("has_audio") val hasAudio: Boolean,
    @SerialName("has_book") val hasBook: Boolean,
    val files: List<SyncFileDto> = emptyList(),
)

@Serializable
data class TombstoneDto(
    val id: String,
    val version: Int,
    @SerialName("deleted_at") val deletedAt: Long,
    val epoch: String,
)

@Serializable
data class ManifestDto(
    val items: List<SyncItemDto> = emptyList(),
    val tombstones: List<TombstoneDto> = emptyList(),
    @SerialName("next_cursor") val nextCursor: String,
    @SerialName("has_more") val hasMore: Boolean,
    val epoch: String,
)

@Serializable
data class SyncStateItemDto(
    val id: String,
    @SerialName("state_seq") val stateSeq: Long,
    @SerialName("audio_position_sec") val audioPositionSec: Double,
    @SerialName("book_locator") val bookLocator: String? = null,
    @SerialName("consumption_state") val consumptionState: String,
    @SerialName("last_consumed_at") val lastConsumedAt: Long? = null,
)

@Serializable
data class SyncStateDto(
    val items: List<SyncStateItemDto> = emptyList(),
    @SerialName("next_cursor") val nextCursor: String,
    @SerialName("has_more") val hasMore: Boolean,
    val epoch: String,
)
