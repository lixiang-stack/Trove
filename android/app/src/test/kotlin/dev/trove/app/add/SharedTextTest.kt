package dev.trove.app.add

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SharedTextTest {
    @Test
    fun extractsFirstUrlAndTrimsTrailingPunctuation() {
        assertEquals(
            "https://www.bilibili.com/video/BV1xx411c7mD",
            firstSharedUrl("看看这个 https://www.bilibili.com/video/BV1xx411c7mD，很有趣"),
        )
    }

    @Test
    fun ignoresTextWithoutUrl() {
        assertNull(firstSharedUrl("一段没有链接的分享文本"))
        assertNull(firstSharedUrl(null))
    }

    @Test
    fun keepsQueryAndFragment() {
        assertEquals(
            "https://youtu.be/abc?t=10",
            firstSharedUrl("https://youtu.be/abc?t=10)."),
        )
    }
}
