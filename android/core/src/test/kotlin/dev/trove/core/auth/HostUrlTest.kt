package dev.trove.core.auth

import org.junit.Assert.assertEquals
import org.junit.Test

class HostUrlTest {
    @Test
    fun httpsUrlIsNormalizedWithoutTrailingSlash() {
        assertEquals(
            HostUrlResult.Valid("https://trove.example.ts.net"),
            HostUrl.normalize(" https://trove.example.ts.net/ ", allowDebugCleartext = false),
        )
        assertEquals(
            HostUrlResult.Valid("https://host.example:8443"),
            HostUrl.normalize("https://HOST.example:8443", allowDebugCleartext = false),
        )
    }

    @Test
    fun missingSchemeDefaultsToHttps() {
        assertEquals(
            HostUrlResult.Valid("https://trove.example"),
            HostUrl.normalize("trove.example", allowDebugCleartext = false),
        )
    }

    @Test
    fun cleartextIsRejectedInRelease() {
        assertEquals(
            HostUrlResult.Invalid(HostUrlError.CLEARTEXT),
            HostUrl.normalize("http://192.168.1.10:8765", allowDebugCleartext = false),
        )
        assertEquals(
            HostUrlResult.Invalid(HostUrlError.CLEARTEXT),
            HostUrl.normalize("http://localhost:8765", allowDebugCleartext = false),
        )
    }

    @Test
    fun debugAllowsOnlyLoopbackCleartext() {
        assertEquals(
            HostUrlResult.Valid("http://localhost:8765"),
            HostUrl.normalize("http://localhost:8765/", allowDebugCleartext = true),
        )
        assertEquals(
            HostUrlResult.Valid("http://10.0.2.2:8765"),
            HostUrl.normalize("http://10.0.2.2:8765", allowDebugCleartext = true),
        )
        assertEquals(
            HostUrlResult.Invalid(HostUrlError.CLEARTEXT),
            HostUrl.normalize("http://192.168.1.10:8765", allowDebugCleartext = true),
        )
    }

    @Test
    fun lanBuildAllowsOnlyPrivateCleartextHosts() {
        assertEquals(
            HostUrlResult.Valid("http://192.168.1.10:8765"),
            HostUrl.normalize(
                "http://192.168.1.10:8765",
                allowDebugCleartext = true,
                allowLanCleartext = true,
            ),
        )
        assertEquals(
            HostUrlResult.Valid("http://172.16.0.5"),
            HostUrl.normalize(
                "http://172.16.0.5",
                allowDebugCleartext = false,
                allowLanCleartext = true,
            ),
        )
        assertEquals(
            HostUrlResult.Valid("http://trove.local:8765"),
            HostUrl.normalize(
                "http://trove.local:8765",
                allowDebugCleartext = false,
                allowLanCleartext = true,
            ),
        )
        for (host in listOf(
            "http://8.8.8.8",
            "http://172.32.0.1",
            "http://example.com",
            "http://0.0.0.0",
        )) {
            assertEquals(
                HostUrlResult.Invalid(HostUrlError.CLEARTEXT),
                HostUrl.normalize(
                    host,
                    allowDebugCleartext = true,
                    allowLanCleartext = true,
                ),
            )
        }
    }

    @Test
    fun unsupportedShapesAreRejected() {
        assertEquals(
            HostUrlResult.Invalid(HostUrlError.EMPTY),
            HostUrl.normalize("   ", allowDebugCleartext = false),
        )
        assertEquals(
            HostUrlResult.Invalid(HostUrlError.UNSUPPORTED_PATH),
            HostUrl.normalize("https://host.example/trove", allowDebugCleartext = false),
        )
        assertEquals(
            HostUrlResult.Invalid(HostUrlError.INVALID),
            HostUrl.normalize("https://user:pass@host.example", allowDebugCleartext = false),
        )
        assertEquals(
            HostUrlResult.Invalid(HostUrlError.INVALID),
            HostUrl.normalize("https://host.example?token=abc", allowDebugCleartext = false),
        )
    }
}
