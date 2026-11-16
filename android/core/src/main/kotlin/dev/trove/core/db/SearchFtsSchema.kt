package dev.trove.core.db

internal object SearchFtsSchema {
    const val CREATE = """
        CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
            norm_text,
            text UNINDEXED,
            item_id UNINDEXED,
            doc_kind UNINDEXED,
            ref UNINDEXED,
            tokenize = 'porter unicode61'
        )
    """
}
