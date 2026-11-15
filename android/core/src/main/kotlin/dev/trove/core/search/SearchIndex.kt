package dev.trove.core.search

import android.database.Cursor
import androidx.sqlite.db.SupportSQLiteDatabase
import dev.trove.core.db.SearchFtsSchema
import dev.trove.core.db.TroveDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

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

    suspend fun replaceItem(itemId: String, documents: List<SearchDocument>) =
        mutex.withLock {
            ensureTable()
            val db = database.openHelper.writableDatabase
            db.beginTransaction()
            try {
                db.execSQL("DELETE FROM search_fts WHERE item_id = ?", arrayOf(itemId))
                for (document in documents) {
                    val normalized = normText(document.text)
                    if (normalized.isEmpty()) continue
                    db.execSQL(
                        "INSERT INTO search_fts (norm_text, text, item_id, doc_kind, ref) " +
                            "VALUES (?, ?, ?, ?, ?)",
                        arrayOf(
                            normalized,
                            document.text,
                            itemId,
                            document.docKind,
                            document.ref,
                        ),
                    )
                }
                db.setTransactionSuccessful()
            } finally {
                db.endTransaction()
            }
        }

    suspend fun deleteItem(itemId: String) = mutex.withLock {
        ensureTable()
        database.openHelper.writableDatabase.execSQL(
            "DELETE FROM search_fts WHERE item_id = ?",
            arrayOf(itemId),
        )
    }

    suspend fun clear() = mutex.withLock {
        ensureTable()
        database.openHelper.writableDatabase.execSQL("DELETE FROM search_fts")
    }

    suspend fun hasDocuments(): Boolean = mutex.withLock {
        runCatching {
            ensureTable()
            database.openHelper.readableDatabase.query("SELECT 1 FROM search_fts LIMIT 1").use {
                it.moveToFirst()
            }
        }.getOrDefault(false)
    }

    suspend fun search(query: String, limit: Int = 100): List<SearchHit> {
        val match = buildMatchQuery(query)
        if (match.match == null && match.likeTerms.isEmpty()) return emptyList()
        return mutex.withLock {
            ensureTable()
            if (available != true) throw LocalSearchUnavailableException()
            val fetchLimit = maxOf(limit * FETCH_MULTIPLIER, 200)
            val hits = linkedMapOf<Triple<String, String, String>, SearchHit>()
            val db = database.openHelper.writableDatabase
            if (match.match != null) {
                db.query(
                    "SELECT item_id, doc_kind, ref, text, (-bm25(search_fts)) AS score " +
                        "FROM search_fts WHERE search_fts MATCH ? ORDER BY score DESC LIMIT ?",
                    arrayOf<Any?>(match.match, fetchLimit),
                ).use { cursor ->
                    while (cursor.moveToNext()) {
                        val hit = cursor.toHit()
                        if (match.likeTerms.isNotEmpty() && !matchesAll(hit.text, match.likeTerms)) {
                            continue
                        }
                        collect(hits, hit)
                    }
                }
            }
            for (term in match.likeTerms) {
                val sql = if (match.match == null) {
                    "SELECT item_id, doc_kind, ref, text FROM search_fts WHERE text LIKE ? LIMIT ?"
                } else {
                    "SELECT item_id, doc_kind, ref, text FROM search_fts " +
                        "WHERE search_fts MATCH ? AND text LIKE ? LIMIT ?"
                }
                val args = if (match.match == null) {
                    arrayOf<Any?>("%$term%", fetchLimit)
                } else {
                    arrayOf<Any?>(match.match, "%$term%", fetchLimit)
                }
                db.query(sql, args).use { cursor ->
                    while (cursor.moveToNext()) {
                        val hit = cursor.toHit(score = LIKE_SCORE)
                        if (!matchesAll(hit.text, match.likeTerms)) continue
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

    private fun ensureTable() {
        if (tableReady) return
        val db = database.openHelper.writableDatabase
        available = try {
            db.execSQL(SearchFtsSchema.CREATE)
            db.execSQL("CREATE VIRTUAL TABLE IF NOT EXISTS temp.search_fts_check USING fts5(x)")
            db.execSQL("DROP TABLE IF EXISTS temp.search_fts_check")
            true
        } catch (_: Exception) {
            false
        }
        tableReady = available == true
        if (available == false) throw LocalSearchUnavailableException()
    }

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

    private fun Cursor.toHit(score: Double? = null): SearchHit = SearchHit(
        itemId = getString(getColumnIndexOrThrow("item_id")),
        docKind = getString(getColumnIndexOrThrow("doc_kind")),
        ref = getString(getColumnIndexOrThrow("ref")),
        text = getString(getColumnIndexOrThrow("text")),
        score = score ?: getDouble(getColumnIndexOrThrow("score")),
    )
}

data class GroupedSearchHits(
    val itemId: String,
    val score: Double,
    val evidence: List<SearchHit>,
)
