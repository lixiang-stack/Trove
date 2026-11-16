package dev.trove.core.search

import androidx.room.PooledConnection
import androidx.room.immediateTransaction
import androidx.room.useReaderConnection
import androidx.room.useWriterConnection
import androidx.sqlite.SQLiteStatement
import dev.trove.core.db.SearchFtsSchema
import dev.trove.core.db.TroveDatabase
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

data class SearchDocument(
    val text: String,
    val docKind: String,
    val ref: String,
)

data class SearchHit(
    val itemId: String,
    val docKind: String,
    val ref: String,
    val text: String,
    val score: Double,
)

class LocalSearchUnavailableException(
    message: String = "SQLite FTS5 is not available",
) : IllegalStateException(message)

private const val FETCH_MULTIPLIER = 30
private const val EVIDENCE_PER_ITEM = 3
private const val KIND_WEIGHT_TITLE = 3.0
private const val KIND_WEIGHT_SUMMARY = 2.0
private const val KIND_WEIGHT_TAG = 2.0
private const val KIND_WEIGHT_CONTENT = 1.0
private const val LIKE_SCORE = 1.0

class SearchIndex(private val database: TroveDatabase) {
    private val mutex = Mutex()
    private var tableReady = false
    private var available: Boolean? = null

    suspend fun isAvailable(): Boolean = mutex.withLock {
        runCatching { ensureTable() }.isSuccess
    }

    suspend fun hasDocuments(): Boolean = mutex.withLock {
        runCatching {
            ensureTable()
            read { connection ->
                connection.query("SELECT 1 FROM search_fts LIMIT 1") { it.getLong(0) }
            }.isNotEmpty()
        }.getOrDefault(false)
    }

    suspend fun replaceItem(itemId: String, documents: List<SearchDocument>) =
        mutex.withLock {
            ensureTable()
            write { connection ->
                connection.exec("DELETE FROM search_fts WHERE item_id = ?", listOf(itemId))
                for (document in documents) {
                    val normalized = normText(document.text)
                    if (normalized.isEmpty()) continue
                    connection.exec(
                        "INSERT INTO search_fts (norm_text, text, item_id, doc_kind, ref) " +
                            "VALUES (?, ?, ?, ?, ?)",
                        listOf(
                            normalized,
                            document.text,
                            itemId,
                            document.docKind,
                            document.ref,
                        ),
                    )
                }
            }
        }

    suspend fun deleteItem(itemId: String) = mutex.withLock {
        ensureTable()
        write { connection ->
            connection.exec("DELETE FROM search_fts WHERE item_id = ?", listOf(itemId))
        }
    }

    suspend fun clear() = mutex.withLock {
        ensureTable()
        write { connection ->
            connection.exec("DELETE FROM search_fts")
        }
    }

    suspend fun search(query: String, limit: Int = 100): List<SearchHit> {
        val match = buildMatchQuery(query)
        if (match.match == null && match.likeTerms.isEmpty()) return emptyList()
        return mutex.withLock {
            ensureTable()
            if (available != true) throw LocalSearchUnavailableException()
            val fetchLimit = maxOf(limit * FETCH_MULTIPLIER, 200)
            val hits = linkedMapOf<Triple<String, String, String>, SearchHit>()
            read { connection ->
                if (match.match != null) {
                    connection.query(
                        "SELECT item_id, doc_kind, ref, text, (-bm25(search_fts)) AS score " +
                            "FROM search_fts WHERE search_fts MATCH ? ORDER BY score DESC LIMIT ?",
                        listOf(match.match, fetchLimit),
                    ) { cursor ->
                        cursor.readHit()
                    }.forEach { hit ->
                        if (match.likeTerms.isNotEmpty() && !matchesAll(hit.text, match.likeTerms)) {
                            return@forEach
                        }
                        collect(hits, hit)
                    }
                }
                for (term in match.likeTerms) {
                    val sql = if (match.match == null) {
                        "SELECT item_id, doc_kind, ref, text, $LIKE_SCORE AS score " +
                            "FROM search_fts WHERE text LIKE ? LIMIT ?"
                    } else {
                        "SELECT item_id, doc_kind, ref, text, $LIKE_SCORE AS score " +
                            "FROM search_fts WHERE search_fts MATCH ? AND text LIKE ? LIMIT ?"
                    }
                    val args = if (match.match == null) {
                        listOf("%$term%", fetchLimit)
                    } else {
                        listOf(match.match, "%$term%", fetchLimit)
                    }
                    connection.query(sql, args) { cursor ->
                        cursor.readHit()
                    }.forEach { hit ->
                        if (!matchesAll(hit.text, match.likeTerms)) return@forEach
                        collect(hits, hit)
                    }
                }
            }
            hits.values.toList()
        }
    }

    fun group(hits: List<SearchHit>, limit: Int = 50): List<GroupedSearchHits> {
        val grouped = linkedMapOf<String, MutableList<SearchHit>>()
        for (hit in hits) {
            grouped.getOrPut(hit.itemId) { mutableListOf() } += hit.copy(
                score = hit.score * weight(hit.docKind)
            )
        }
        val results = grouped.map { (itemId, itemHits) ->
            val sorted = itemHits.sortedWith(
                compareByDescending<SearchHit> { it.score }.thenBy { it.ref }
            )
            val evidence = mutableListOf<SearchHit>()
            val seen = mutableSetOf<Pair<String, String>>()
            for (hit in sorted) {
                if (!seen.add(hit.docKind to hit.ref)) continue
                evidence += hit
                if (evidence.size == EVIDENCE_PER_ITEM) break
            }
            GroupedSearchHits(itemId = itemId, score = evidence.first().score, evidence = evidence)
        }
        return results
            .sortedWith(compareByDescending<GroupedSearchHits> { it.score }.thenBy { it.itemId })
            .take(limit)
    }

    private suspend fun ensureTable() {
        if (tableReady) return
        available = try {
            write { connection ->
                connection.exec(SearchFtsSchema.CREATE)
                connection.exec("CREATE VIRTUAL TABLE IF NOT EXISTS temp.search_fts_check USING fts5(x)")
                connection.exec("DROP TABLE IF EXISTS temp.search_fts_check")
            }
            true
        } catch (_: Exception) {
            false
        }
        tableReady = available == true
        if (available == false) throw LocalSearchUnavailableException()
    }

    private suspend fun write(block: suspend (PooledConnection) -> Unit) {
        database.useWriterConnection { transactor ->
            transactor.immediateTransaction { block(this) }
        }
    }

    private suspend fun <T> read(block: suspend (PooledConnection) -> T): T =
        database.useReaderConnection { connection -> block(connection) }

    private suspend fun PooledConnection.exec(sql: String, args: List<Any?> = emptyList()) {
        usePrepared(sql) { statement ->
            statement.bind(args)
            statement.step()
        }
    }

    private suspend fun <T> PooledConnection.query(
        sql: String,
        args: List<Any?> = emptyList(),
        map: (SQLiteStatement) -> T,
    ): List<T> {
        val rows = mutableListOf<T>()
        usePrepared(sql) { statement ->
            statement.bind(args)
            while (statement.step()) {
                rows += map(statement)
            }
        }
        return rows
    }

    private fun SQLiteStatement.bind(args: List<Any?>) {
        for ((index, value) in args.withIndex()) {
            val position = index + 1
            when (value) {
                null -> bindNull(position)
                is Long -> bindLong(position, value)
                is Int -> bindLong(position, value.toLong())
                is Double -> bindDouble(position, value)
                is Float -> bindDouble(position, value.toDouble())
                else -> bindText(position, value.toString())
            }
        }
    }

    private fun SQLiteStatement.readHit(): SearchHit = SearchHit(
        itemId = getText(0),
        docKind = getText(1),
        ref = getText(2),
        text = getText(3),
        score = getDouble(4),
    )

    private fun weight(docKind: String): Double = when (docKind) {
        "title" -> KIND_WEIGHT_TITLE
        "summary" -> KIND_WEIGHT_SUMMARY
        "tag" -> KIND_WEIGHT_TAG
        else -> KIND_WEIGHT_CONTENT
    }

    private fun collect(
        hits: MutableMap<Triple<String, String, String>, SearchHit>,
        hit: SearchHit,
    ) {
        val key = Triple(hit.itemId, hit.docKind, hit.ref)
        val existing = hits[key]
        if (existing == null || hit.score > existing.score) {
            hits[key] = hit
        }
    }

    private fun matchesAll(value: String, terms: List<String>): Boolean {
        val normalized = normalizeText(value)
        return terms.all { normalized.contains(it) }
    }
}

data class GroupedSearchHits(
    val itemId: String,
    val score: Double,
    val evidence: List<SearchHit>,
)
