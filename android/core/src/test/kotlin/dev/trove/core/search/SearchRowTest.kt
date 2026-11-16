package dev.trove.core.search

import androidx.sqlite.SQLiteStatement
import org.junit.Assert.assertEquals
import org.junit.Test

class SearchRowTest {
    @Test
    fun readsFiveColumnsWithZeroBasedIndexes() {
        val statement = FakeStatement(
            listOf(
                "item-1",
                "transcript",
                "3:65000",
                "人工智能正在改变记忆方式",
                3.5,
            )
        )

        val hit = statement.readSearchHit()

        assertEquals("item-1", hit.itemId)
        assertEquals("transcript", hit.docKind)
        assertEquals("3:65000", hit.ref)
        assertEquals("人工智能正在改变记忆方式", hit.text)
        assertEquals(3.5, hit.score, 0.0)
    }

    @Test(expected = IndexOutOfBoundsException::class)
    fun readsPastTheLastColumnFailLoudly() {
        FakeStatement(listOf("only-one-column")).getDouble(4)
    }

    private class FakeStatement(private val values: List<Any?>) : SQLiteStatement {
        override fun bindBlob(index: Int, value: ByteArray) = unsupported()
        override fun bindDouble(index: Int, value: Double) = unsupported()
        override fun bindLong(index: Int, value: Long) = unsupported()
        override fun bindText(index: Int, value: String) = unsupported()
        override fun bindNull(index: Int) = unsupported()
        override fun getBlob(index: Int): ByteArray = unsupported()
        override fun getDouble(index: Int): Double = values[index] as Double
        override fun getLong(index: Int): Long = values[index] as Long
        override fun getText(index: Int): String = values[index] as String
        override fun isNull(index: Int): Boolean = values[index] == null
        override fun getColumnCount(): Int = values.size
        override fun getColumnName(index: Int): String = "column-$index"
        override fun getColumnType(index: Int): Int = 0
        override fun step(): Boolean = false
        override fun reset() = Unit
        override fun clearBindings() = Unit
        override fun close() = Unit

        private fun unsupported(): Nothing = error("unused in this test")
    }
}
