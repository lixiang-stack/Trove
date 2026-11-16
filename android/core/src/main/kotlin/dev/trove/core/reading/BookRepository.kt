package dev.trove.core.reading

import dev.trove.core.db.BookChapterEntity
import dev.trove.core.db.BookParagraphEntity
import dev.trove.core.db.TroveDatabase
import dev.trove.core.db.writeTransaction
import dev.trove.core.storage.ArtifactFileStore
import java.io.File
import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
private data class BookDocumentDto(
    val title: String = "",
    val author: String? = null,
    val language: String? = null,
    val chapters: List<BookChapterDto> = emptyList(),
)

@Serializable
private data class BookChapterDto(
    @SerialName("chapter_index") val chapterIndex: Int,
    val title: String? = null,
    val html: String = "",
    val text: String = "",
    val paragraphs: List<String> = emptyList(),
)

sealed interface BookLoadResult {
    data class Ready(val chapterCount: Int) : BookLoadResult

    data object NotDownloaded : BookLoadResult

    data object Failed : BookLoadResult
}

class BookRepository(
    private val database: TroveDatabase,
    private val fileStore: ArtifactFileStore,
    private val json: Json = Json { ignoreUnknownKeys = true },
) {
    fun observeChapters(itemId: String): Flow<List<BookChapterEntity>> =
        database.bookDao().observeChapters(itemId)

    suspend fun chapters(itemId: String): List<BookChapterEntity> =
        database.bookDao().chapters(itemId)

    suspend fun chapter(itemId: String, chapterIndex: Int): BookChapterEntity? =
        database.bookDao().chapter(itemId, chapterIndex)

    suspend fun epubFile(itemId: String): File? {
        val artifact = database.artifactDao().find(itemId, "book") ?: return null
        if (artifact.downloadState != "completed") return null
        return fileStore.existingFile(itemId, "book", artifact.localPath)
    }

    suspend fun ensureParsed(itemId: String): BookLoadResult {
        val artifact = database.artifactDao().find(itemId, "book_json")
            ?: return BookLoadResult.NotDownloaded
        if (artifact.downloadState != "completed") return BookLoadResult.NotDownloaded
        val file = fileStore.existingFile(itemId, "book_json", artifact.localPath)
            ?: return BookLoadResult.NotDownloaded
        if (database.bookDao().chapterCount(itemId) > 0) {
            return BookLoadResult.Ready(database.bookDao().chapterCount(itemId))
        }
        return parseFile(itemId, file)
    }

    suspend fun parseFile(itemId: String, file: File): BookLoadResult {
        val document = try {
            json.decodeFromString<BookDocumentDto>(file.readText())
        } catch (_: Exception) {
            return BookLoadResult.Failed
        }
        if (document.chapters.isEmpty()) return BookLoadResult.Failed
        database.writeTransaction {
            database.bookDao().deleteForItem(itemId)
            database.bookDao().deleteParagraphsForItem(itemId)
            database.bookDao().insertChapters(
                document.chapters.map {
                    BookChapterEntity(
                        itemId = itemId,
                        chapterIndex = it.chapterIndex,
                        title = it.title,
                        html = it.html,
                        text = it.text,
                    )
                }
            )
            database.bookDao().insertParagraphs(
                document.chapters.flatMap { chapter ->
                    chapter.paragraphs.mapIndexed { index, paragraph ->
                        BookParagraphEntity(
                            itemId = itemId,
                            chapterIndex = chapter.chapterIndex,
                            paragraphIndex = index,
                            text = paragraph,
                        )
                    }
                }
            )
        }
        return BookLoadResult.Ready(document.chapters.size)
    }
}
