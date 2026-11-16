package dev.trove.app.add

private val URL_PATTERN = Regex(
    """https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+""",
    RegexOption.IGNORE_CASE,
)
private val TRAILING_PUNCTUATION = Regex("""[),.;!?，。；：！？）】》]+$""")

fun firstSharedUrl(text: String?): String? {
    val match = URL_PATTERN.find(text.orEmpty()) ?: return null
    return TRAILING_PUNCTUATION.replace(match.value, "")
}
