package dev.trove.app.library

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import dev.trove.app.R
import dev.trove.app.ui.components.TroveChip
import dev.trove.core.library.LibraryItem

data class TagOption(val name: String, val count: Int)

private const val INITIAL_VISIBLE_TAGS = 12

/** Count each tag once per Item and put shared tags first. */
fun tagOptions(items: List<LibraryItem>): List<TagOption> {
    val counts = mutableMapOf<String, Int>()
    for (item in items) {
        for (tag in item.tags.distinct()) {
            counts[tag] = (counts[tag] ?: 0) + 1
        }
    }
    return counts.map { TagOption(it.key, it.value) }
        .sortedWith(compareByDescending<TagOption> { it.count }.thenBy { it.name.lowercase() })
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TagFilterSection(
    options: List<TagOption>,
    selected: String?,
    onSelect: (String?) -> Unit,
) {
    if (options.isEmpty()) return
    var expanded by remember { mutableStateOf(false) }
    val ordered = if (selected == null) {
        options
    } else {
        val match = options.firstOrNull { it.name == selected }
        if (match == null) options else listOf(match) + options.filter { it.name != selected }
    }
    val visible = if (expanded) ordered else ordered.take(INITIAL_VISIBLE_TAGS)
    Text(
        stringResource(R.string.filter_tag),
        style = MaterialTheme.typography.titleSmall,
        modifier = Modifier.padding(top = 10.dp),
    )
    FlowRow(
        modifier = Modifier.padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        visible.forEach { option ->
            TroveChip(
                label = option.name,
                selected = selected == option.name,
                onClick = { onSelect(if (selected == option.name) null else option.name) },
                modifier = Modifier.testTag("filter-option-${option.name}"),
            )
        }
        if (options.size > INITIAL_VISIBLE_TAGS) {
            TroveChip(
                label = if (expanded) {
                    stringResource(R.string.filter_tag_less)
                } else {
                    stringResource(R.string.filter_tag_more, options.size - INITIAL_VISIBLE_TAGS)
                },
                selected = false,
                onClick = { expanded = !expanded },
                modifier = Modifier.testTag("filter-tags-toggle"),
            )
        }
    }
}
