package dev.trove.reader

import dev.trove.core.db.TroveDatabase
import dev.trove.core.library.ItemMutationRepository
import dev.trove.core.library.LibraryRepository
import dev.trove.core.reading.BookRepository

data class ReaderDependencies(
    val database: TroveDatabase,
    val libraryRepository: LibraryRepository,
    val bookRepository: BookRepository,
    val itemMutationRepository: ItemMutationRepository,
)

/**
 * The app owns the Room instance; the reader runs in the same process and must
 * share it so progress written while reading is visible to the app immediately.
 */
interface ReaderHost {
    val readerDependencies: ReaderDependencies?
}
