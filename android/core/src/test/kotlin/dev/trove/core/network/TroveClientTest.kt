package dev.trove.core.network

import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class TroveClientTest {
    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.close()
    }

    private fun baseUrl(): String = server.url("/").toString()

    @Test
    fun bearerTokenIsAddedByInterceptor() = runBlocking {
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .addHeader("Content-Type", "application/json")
                .body("""{"api_version":"1","capabilities":{"sync":true}}""")
                .build()
        )
        val client = TroveClient(
            RetrofitTroveApiFactory().create(baseUrl(), "secret-token")
        )
        client.health()
        val request = server.takeRequest()
        assertEquals("Bearer secret-token", request.headers["Authorization"])
    }

    @Test
    fun unauthenticatedClientSendsNoBearerHeader() = runBlocking {
        server.enqueue(
            MockResponse.Builder()
                .code(200)
                .addHeader("Content-Type", "application/json")
                .body("""{"api_version":"1","capabilities":{}}""")
                .build()
        )
        val client = TroveClient(RetrofitTroveApiFactory().create(baseUrl(), null))
        client.health()
        assertNull(server.takeRequest().headers["Authorization"])
    }

    @Test
    fun errorBodyIsParsedAndUnauthorizedListenerFires() = runBlocking {
        server.enqueue(
            MockResponse.Builder()
                .code(401)
                .addHeader("Content-Type", "application/json")
                .body(
                    """
                    {"code":"auth.device_revoked",
                     "message":"Device authorization has been revoked",
                     "details":null}
                    """.trimIndent()
                )
                .build()
        )
        var unauthorizedCode: String? = null
        val client = TroveClient(
            RetrofitTroveApiFactory().create(baseUrl(), "secret-token"),
            UnauthorizedListener { unauthorizedCode = it },
        )
        try {
            client.health()
            fail("expected an API exception")
        } catch (error: TroveApiException) {
            assertEquals("auth.device_revoked", error.code)
            assertEquals(401, error.statusCode)
            assertEquals("Device authorization has been revoked", error.message)
        }
        assertEquals("auth.device_revoked", unauthorizedCode)
    }

    @Test
    fun rateLimitCarriesRetryAfter() = runBlocking {
        server.enqueue(
            MockResponse.Builder()
                .code(429)
                .addHeader("Content-Type", "application/json")
                .addHeader("Retry-After", "30")
                .body("""{"code":"auth.rate_limited","message":"Too many attempts"}""")
                .build()
        )
        val client = TroveClient(RetrofitTroveApiFactory().create(baseUrl(), null))
        try {
            client.health()
            fail("expected an API exception")
        } catch (error: TroveApiException) {
            assertEquals(429, error.statusCode)
            assertEquals(30L, error.retryAfterSeconds)
        }
    }

    @Test
    fun deleteItemKeepsStableHostErrorCode() = runBlocking {
        server.enqueue(
            MockResponse.Builder()
                .code(404)
                .addHeader("Content-Type", "application/json")
                .body("""{"code":"item.not_found","message":"Item not found"}""")
                .build()
        )
        val client = TroveClient(RetrofitTroveApiFactory().create(baseUrl(), "token"))
        try {
            client.deleteItem("missing")
            fail("expected an API exception")
        } catch (error: TroveApiException) {
            assertEquals("item.not_found", error.code)
            assertEquals(404, error.statusCode)
        }
    }

    @Test
    fun revokeDeviceFailureIsNotSilentlyIgnored() = runBlocking {
        server.enqueue(
            MockResponse.Builder()
                .code(401)
                .addHeader("Content-Type", "application/json")
                .body("""{"code":"auth.device_revoked","message":"Revoked"}""")
                .build()
        )
        val client = TroveClient(RetrofitTroveApiFactory().create(baseUrl(), "token"))
        try {
            client.revokeDevice("device-1")
            fail("expected an API exception")
        } catch (error: TroveApiException) {
            assertEquals("auth.device_revoked", error.code)
        }
    }
}
