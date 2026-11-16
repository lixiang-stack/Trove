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

@Serializable
data class BookLocatorDto(
    val schema: Int = 2,
    @SerialName("chapter_index") val chapterIndex: Int,
    @SerialName("paragraph_index") val paragraphIndex: Int? = null,
    @SerialName("scroll_ratio") val scrollRatio: Double = 0.0,
    @SerialName("epub_href") val epubHref: String? = null,
    @SerialName("epub_progression") val epubProgression: Double? = null,
    @SerialName("epub_total_progression") val epubTotalProgression: Double? = null,
)

@Serializable
data class ProgressRequestDto(
    @SerialName("position_sec") val positionSec: Double? = null,
    @SerialName("consumption_state") val consumptionState: String? = null,
    @SerialName("book_locator") val bookLocator: BookLocatorDto? = null,
    @SerialName("client_updated_at") val clientUpdatedAt: Long? = null,
)

@Serializable
data class TagsRequestDto(
    val tags: List<String>,
    @SerialName("client_updated_at") val clientUpdatedAt: Long? = null,
)

@Serializable
data class ItemCreateRequestDto(
    val kind: String,
    val url: String? = null,
    @SerialName("feed_url") val feedUrl: String? = null,
    @SerialName("episode_guid") val episodeGuid: String? = null,
    @SerialName("enclosure_url") val enclosureUrl: String? = null,
)

@Serializable
data class ArtifactDto(
    val kind: String,
    val sha256: String = "",
    val size: Long = 0,
    val mime: String = "",
    @SerialName("duration_sec") val durationSec: Double? = null,
    val url: String? = null,
)

@Serializable
data class ItemDto(
    val id: String,
    val version: Int = 0,
    @SerialName("source_type") val sourceType: String = "video_url",
    val platform: String = "",
    val title: String = "",
    val author: String? = null,
    @SerialName("published_at") val publishedAt: String? = null,
    @SerialName("fetched_at") val fetchedAt: Long? = null,
    val language: String? = null,
    @SerialName("duration_sec") val durationSec: Double? = null,
    val summary: String? = null,
    val tags: List<String> = emptyList(),
    @SerialName("source_type_label") val sourceTypeLabel: String? = null,
    @SerialName("consumption_label") val consumptionLabel: String? = null,
    @SerialName("processing_label") val processingLabel: String? = null,
    @SerialName("has_cover") val hasCover: Boolean = false,
    @SerialName("cover_url") val coverUrl: String? = null,
    val artifacts: List<ArtifactDto> = emptyList(),
    @SerialName("processing_state") val processingState: String = "queued",
    @SerialName("error_code") val errorCode: String? = null,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("has_audio") val hasAudio: Boolean = false,
    @SerialName("has_book") val hasBook: Boolean = false,
    @SerialName("consumption_state") val consumptionState: String = "unstarted",
    @SerialName("audio_position_sec") val audioPositionSec: Double = 0.0,
    @SerialName("book_locator") val bookLocator: String? = null,
)

@Serializable
data class ItemCreateResponseDto(
    val item: ItemDto,
    val deduplicated: Boolean = false,
)

@Serializable
data class FeedPreviewRequestDto(
    val url: String,
)

@Serializable
data class FeedEpisodeDto(
    val guid: String? = null,
    val title: String,
    val author: String? = null,
    @SerialName("published_at") val publishedAt: String? = null,
    @SerialName("duration_sec") val durationSec: Double? = null,
    @SerialName("enclosure_url") val enclosureUrl: String,
    @SerialName("enclosure_type") val enclosureType: String? = null,
    @SerialName("enclosure_size") val enclosureSize: Long? = null,
)

@Serializable
data class FeedPreviewResponseDto(
    val title: String,
    val author: String? = null,
    val link: String? = null,
    val episodes: List<FeedEpisodeDto> = emptyList(),
)

@Serializable
data class SearchEvidenceDto(
    @SerialName("doc_kind") val docKind: String,
    val ref: String,
    val text: String,
    val snippet: String,
    val score: Double = 0.0,
    val url: String? = null,
)

@Serializable
data class SearchResultDto(
    val item: ItemDto,
    val score: Double = 0.0,
    val evidence: List<SearchEvidenceDto> = emptyList(),
)

@Serializable
data class SearchResponseDto(
    val query: String = "",
    val results: List<SearchResultDto> = emptyList(),
    val count: Int = 0,
    val limit: Int? = null,
    val offset: Int = 0,
)

@Serializable
data class MutationItemDto(
    val id: String,
    val version: Int = 0,
    @SerialName("audio_position_sec") val audioPositionSec: Double = 0.0,
    @SerialName("book_locator") val bookLocator: String? = null,
    @SerialName("consumption_state") val consumptionState: String = "unstarted",
    val tags: List<String> = emptyList(),
)

@Serializable
data class FieldClockDto(
    @SerialName("client_updated_at") val clientUpdatedAt: Long,
    @SerialName("device_id") val deviceId: String,
)

@Serializable
data class MutationResponseDto(
    val ok: Boolean = true,
    val applied: Boolean = true,
    val item: MutationItemDto,
    @SerialName("field_clocks") val fieldClocks: Map<String, FieldClockDto> = emptyMap(),
    val warnings: List<String> = emptyList(),
)
