package dev.trove.app.testing

import androidx.compose.ui.test.junit4.ComposeContentTestRule
import androidx.compose.ui.test.junit4.ComposeTestRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo

/** CI runners are slower than local machines; keep one generous deadline. */
const val COMPOSE_TIMEOUT_MS = 30_000L

/**
 * Wait for a tagged node and pump the main looper, so Room-backed ViewModel
 * coroutines can resume while the Compose clock advances.
 */
fun waitForTag(compose: ComposeTestRule, tag: String, timeoutMillis: Long = COMPOSE_TIMEOUT_MS) {
    compose.waitUntil(timeoutMillis) {
        compose.waitForIdle()
        compose.onAllNodesWithTag(tag).fetchSemanticsNodes().isNotEmpty()
    }
}

fun waitForText(compose: ComposeTestRule, text: String, timeoutMillis: Long = COMPOSE_TIMEOUT_MS) {
    compose.waitUntil(timeoutMillis) {
        compose.waitForIdle()
        compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty()
    }
}

/**
 * Tap a node inside a scrollable screen. Compose tests do not scroll before
 * clicking, so off-screen actions need an explicit [performScrollTo].
 */
fun ComposeContentTestRule.scrollAndClick(tag: String) {
    onNodeWithTag(tag).performScrollTo().performClick()
}

fun ComposeContentTestRule.scrollAndClickText(text: String) {
    onNodeWithText(text).performScrollTo().performClick()
}
