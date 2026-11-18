package dev.trove.core.db

import androidx.room.ColumnInfo
import androidx.room.Embedded
import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index
import androidx.room.Junction
import androidx.room.PrimaryKey
import androidx.room.Relation

@Entity(tableName = "items")
data class ItemEntity(
    @PrimaryKey val id: String,
    val version: Int,
    @ColumnInfo(name = "source_type") val sourceType: String,
    val platform: String,
    @ColumnInfo(name = "collection_id") val collectionId: String? = null,
    @ColumnInfo(name = "collection_index") val collectionIndex: Int? = null,
    @ColumnInfo(name = "collection_title") val collectionTitle: String? = null,
    @ColumnInfo(name = "collection_platform") val collectionPlatform: String? = null,
    @ColumnInfo(name = "collection_source_url") val collectionSourceUrl: String? = null,
    val title: String,
    val author: String?,
    @ColumnInfo(name = "published_at") val publishedAt: String?,
    @ColumnInfo(name = "fetched_at") val fetchedAt: Long,
    val language: String?,
    @ColumnInfo(name = "duration_sec") val durationSec: Double?,
    val summary: String?,
    @ColumnInfo(name = "processing_state") val processingState: String,
    @ColumnInfo(name = "error_code") val errorCode: String?,
    @ColumnInfo(name = "error_message") val errorMessage: String?,
    @ColumnInfo(name = "has_audio") val hasAudio: Boolean,
    @ColumnInfo(name = "has_book") val hasBook: Boolean,
    @ColumnInfo(name = "consumption_state") val consumptionState: String,
    @ColumnInfo(name = "audio_position_sec") val audioPositionSec: Double,
    @ColumnInfo(name = "book_locator") val bookLocator: String?,
    @ColumnInfo(name = "last_consumed_at") val lastConsumedAt: Long?,
    @ColumnInfo(name = "content_seq") val contentSeq: Long,
    @ColumnInfo(name = "state_seq") val stateSeq: Long,
    @ColumnInfo(name = "download_state") val downloadState: String = "none",
    @ColumnInfo(name = "last_synced_at") val lastSyncedAt: Long,
)

@Entity(
    tableName = "artifacts",
    primaryKeys = ["item_id", "kind"],
    foreignKeys = [
        ForeignKey(
            entity = ItemEntity::class,
            parentColumns = ["id"],
            childColumns = ["item_id"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("item_id")],
)
data class ArtifactEntity(
    @ColumnInfo(name = "item_id") val itemId: String,
    val kind: String,
    val sha256: String,
    val size: Long,
    val mime: String,
    val version: Int,
    @ColumnInfo(name = "local_path") val localPath: String?,
    @ColumnInfo(name = "download_state") val downloadState: String = "none",
    @ColumnInfo(name = "downloaded_bytes") val downloadedBytes: Long = 0,
    val etag: String? = null,
    @ColumnInfo(name = "error_code") val errorCode: String? = null,
)

@Entity(
    tableName = "transcript_segments",
    primaryKeys = ["item_id", "seq"],
    foreignKeys = [
        ForeignKey(
            entity = ItemEntity::class,
            parentColumns = ["id"],
            childColumns = ["item_id"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("item_id")],
)
data class TranscriptSegmentEntity(
    @ColumnInfo(name = "item_id") val itemId: String,
    val seq: Int,
    @ColumnInfo(name = "start_ms") val startMs: Long,
    @ColumnInfo(name = "end_ms") val endMs: Long,
    val text: String,
)

@Entity(
    tableName = "book_chapters",
    primaryKeys = ["item_id", "chapter_index"],
    foreignKeys = [
        ForeignKey(
            entity = ItemEntity::class,
            parentColumns = ["id"],
            childColumns = ["item_id"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("item_id")],
)
data class BookChapterEntity(
    @ColumnInfo(name = "item_id") val itemId: String,
    @ColumnInfo(name = "chapter_index") val chapterIndex: Int,
    val title: String?,
    val html: String,
    val text: String,
)

@Entity(
    tableName = "book_paragraphs",
    primaryKeys = ["item_id", "chapter_index", "paragraph_index"],
    foreignKeys = [
        ForeignKey(
            entity = ItemEntity::class,
            parentColumns = ["id"],
            childColumns = ["item_id"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("item_id"), Index("item_id", "chapter_index")],
)
data class BookParagraphEntity(
    @ColumnInfo(name = "item_id") val itemId: String,
    @ColumnInfo(name = "chapter_index") val chapterIndex: Int,
    @ColumnInfo(name = "paragraph_index") val paragraphIndex: Int,
    val text: String,
)

@Entity(tableName = "tags")
data class TagEntity(
    @PrimaryKey @ColumnInfo(name = "normalized_name") val normalizedName: String,
    val name: String,
)

@Entity(
    tableName = "item_tags",
    primaryKeys = ["item_id", "tag_name"],
    foreignKeys = [
        ForeignKey(
            entity = ItemEntity::class,
            parentColumns = ["id"],
            childColumns = ["item_id"],
            onDelete = ForeignKey.CASCADE,
        ),
        ForeignKey(
            entity = TagEntity::class,
            parentColumns = ["normalized_name"],
            childColumns = ["tag_name"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [Index("item_id"), Index("tag_name")],
)
data class ItemTagEntity(
    @ColumnInfo(name = "item_id") val itemId: String,
    @ColumnInfo(name = "tag_name") val tagName: String,
    val source: String,
)

@Entity(tableName = "sync_cursor")
data class SyncCursorEntity(
    @PrimaryKey val id: Int = 1,
    @ColumnInfo(name = "content_cursor") val contentCursor: String?,
    @ColumnInfo(name = "state_cursor") val stateCursor: String?,
    val epoch: String?,
    @ColumnInfo(name = "last_success_at") val lastSuccessAt: Long?,
    @ColumnInfo(name = "error_code") val errorCode: String?,
)

@Entity(tableName = "pending_mutations")
data class PendingMutationEntity(
    @PrimaryKey @ColumnInfo(name = "idempotency_key") val idempotencyKey: String,
    @ColumnInfo(name = "item_id") val itemId: String,
    val field: String,
    @ColumnInfo(name = "payload_json") val payloadJson: String,
    @ColumnInfo(name = "client_updated_at") val clientUpdatedAt: Long,
    @ColumnInfo(name = "created_at") val createdAt: Long,
    @ColumnInfo(name = "retry_count") val retryCount: Int = 0,
    @ColumnInfo(name = "last_error") val lastError: String? = null,
)

@Entity(tableName = "pending_deletions")
data class PendingDeletionEntity(
    @PrimaryKey val path: String,
    @ColumnInfo(name = "item_id") val itemId: String,
)

data class ItemWithDetails(
    @Embedded val item: ItemEntity,
    @Relation(parentColumn = "id", entityColumn = "item_id")
    val artifacts: List<ArtifactEntity>,
    @Relation(
        parentColumn = "id",
        entityColumn = "normalized_name",
        associateBy = Junction(
            value = ItemTagEntity::class,
            parentColumn = "item_id",
            entityColumn = "tag_name",
        ),
    )
    val tags: List<TagEntity>,
)
