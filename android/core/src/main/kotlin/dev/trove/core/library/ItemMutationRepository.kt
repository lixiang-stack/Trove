package dev.trove.core.library

import dev.trove.core.db.ItemTagEntity
import dev.trove.core.db.PendingMutationEntity
import dev.trove.core.db.TagEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.db.writeTransaction
import dev.trove.core.network.BookLocatorDto
import dev.trove.core.network.ProgressRequestDto
import dev.trove.core.network.TagsRequestDto
import dev.trove.core.reading.BookLocator
import dev.trove.core.tags.InvalidTagException
import dev.trove.core.tags.normalizeTags
import java.util.UUID
import kotlinx.serialization.json.Json

private const val AUTO_FINISH_RATIO = 0.95

/**
 * Local optimistic writes for Consumption State, reading position and Tags.
 * Every write is queued as a field mutation so it survives offline use and is
 * reconciled with the Host through field-level last-write-wins.
 */
class ItemMutationRepository(
    private val database: TroveDatabase,
    private val now: () -> Long = System::currentTimeMillis,
    private val onTagsChanged: suspend (String) -> Unit = {},
) {
    private val json = Json { encodeDefaults = true }

    suspend fun setConsumption(itemId: String, state: String) {
        require(state in CONSUMPTION_STATES) { "Invalid consumption state: $state" }
        val timestamp = now()
        database.writeTransaction {
            database.itemDao().applyLocalConsumption(itemId, state, timestamp)
            enqueue(
                itemId = itemId,
                field = CONSUMPTION_STATE,
                payload = ProgressRequestDto(
                    consumptionState = state,
                    clientUpdatedAt = timestamp,
                ),
                timestamp = timestamp,
            )
        }
    }

    suspend fun replaceTags(itemId: String, rawTags: List<String>): List<String> {
        val tags = normalizeTags(rawTags)
        val timestamp = now()
        database.writeTransaction {
            database.tagDao().clearItemTags(itemId)
            if (tags.isNotEmpty()) {
                database.tagDao().upsertAll(
                    tags.map { TagEntity(normalizedName = it.normalizedName, name = it.name) }
                )
                database.tagDao().insertItemTags(
                    tags.map {
                        ItemTagEntity(itemId = itemId, tagName = it.normalizedName, source = "user")
                    }
                )
            }
            enqueue(
                itemId = itemId,
                field = TAGS,
                payload = TagsRequestDto(
                    tags = tags.map { it.name },
                    clientUpdatedAt = timestamp,
                ),
                timestamp = timestamp,
            )
        }
        onTagsChanged(itemId)
        return tags.map { it.name }
    }

    suspend fun saveBookProgress(itemId: String, locator: BookLocator): String {
        val timestamp = now()
        val item = database.itemDao().find(itemId)
            ?: throw IllegalArgumentException("Item not found: $itemId")
        val state = when {
            item.consumptionState == FINISHED -> FINISHED
            locator.fraction >= AUTO_FINISH_RATIO -> FINISHED
            else -> IN_PROGRESS
        }
        val serialized = locator.toJson()
        database.writeTransaction {
            database.itemDao().applyLocalBookProgress(itemId, serialized, state, timestamp)
            enqueue(
                itemId = itemId,
                field = BOOK_PROGRESS,
                payload = ProgressRequestDto(
                    bookLocator = BookLocatorDto(
                        schema = 2,
                        chapterIndex = locator.chapterIndex,
                        paragraphIndex = locator.paragraphIndex,
                        scrollRatio = locator.scrollRatio,
                        epubHref = locator.epubHref,
                        epubProgression = locator.epubProgression,
                        epubTotalProgression = locator.epubTotalProgression,
                    ),
                    consumptionState = state,
                    clientUpdatedAt = timestamp,
                ),
                timestamp = timestamp,
            )
        }
        return serialized
    }

    private suspend fun enqueue(
        itemId: String,
        field: String,
        payload: ProgressRequestDto,
        timestamp: Long,
    ) {
        enqueue(itemId, field, json.encodeToString(payload), timestamp)
    }

    private suspend fun enqueue(
        itemId: String,
        field: String,
        payload: TagsRequestDto,
        timestamp: Long,
    ) {
        enqueue(itemId, field, json.encodeToString(payload), timestamp)
    }

    private suspend fun enqueue(
        itemId: String,
        field: String,
        payloadJson: String,
        timestamp: Long,
    ) {
        database.pendingMutationDao().deleteForField(itemId, field)
        database.pendingMutationDao().upsert(
            PendingMutationEntity(
                idempotencyKey = UUID.randomUUID().toString(),
                itemId = itemId,
                field = field,
                payloadJson = payloadJson,
                clientUpdatedAt = timestamp,
                createdAt = timestamp,
            )
        )
    }

    companion object {
        const val AUDIO_PROGRESS = "audio_progress"
        const val BOOK_PROGRESS = "book_progress"
        const val CONSUMPTION_STATE = "consumption_state"
        const val TAGS = "tags"

        private const val IN_PROGRESS = "in_progress"
        private const val FINISHED = "finished"
        private val CONSUMPTION_STATES = setOf("unstarted", "in_progress", "finished")
    }
}

fun InvalidTagException.toUserMessage(): String = when (code) {
    "tag.empty" -> "Tag 不能为空"
    "tag.too_long" -> "Tag 不能超过 64 个字符"
    else -> message.orEmpty()
}
