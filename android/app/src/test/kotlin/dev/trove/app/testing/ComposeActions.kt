package dev.trove.app.testing

import androidx.compose.ui.test.junit4.ComposeContentTestRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo

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
