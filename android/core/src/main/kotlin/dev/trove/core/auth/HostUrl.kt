package dev.trove.core.auth

import java.net.URI
import java.net.URISyntaxException

sealed interface HostUrlResult {
    data class Valid(val baseUrl: String) : HostUrlResult

    data class Invalid(val reason: HostUrlError) : HostUrlResult
}

enum class HostUrlError {
    EMPTY,
    INVALID,
    CLEARTEXT,
    UNSUPPORTED_PATH,
}

object HostUrl {
    private val debugCleartextHosts = setOf("localhost", "127.0.0.1", "10.0.2.2", "::1")

    fun normalize(raw: String, allowDebugCleartext: Boolean): HostUrlResult {
        val value = raw.trim()
        if (value.isEmpty()) {
            return HostUrlResult.Invalid(HostUrlError.EMPTY)
        }
        val candidate = if ("://" in value) value else "https://$value"
        val uri = try {
            URI(candidate)
        } catch (_: URISyntaxException) {
            return HostUrlResult.Invalid(HostUrlError.INVALID)
        }
        val scheme = uri.scheme?.lowercase()
        val host = uri.host
        if (scheme == null || host == null || uri.userInfo != null) {
            return HostUrlResult.Invalid(HostUrlError.INVALID)
        }
        if (scheme != "https") {
            val hostKey = host.removePrefix("[").removeSuffix("]").lowercase()
            val allowed = scheme == "http" &&
                allowDebugCleartext &&
                hostKey in debugCleartextHosts
            if (!allowed) {
                return HostUrlResult.Invalid(HostUrlError.CLEARTEXT)
            }
        }
        if (uri.query != null || uri.fragment != null) {
            return HostUrlResult.Invalid(HostUrlError.INVALID)
        }
        if (!uri.path.isNullOrEmpty() && uri.path != "/") {
            return HostUrlResult.Invalid(HostUrlError.UNSUPPORTED_PATH)
        }
        val port = if (uri.port == -1) "" else ":${uri.port}"
        return HostUrlResult.Valid("$scheme://${host.lowercase()}$port")
    }
}
