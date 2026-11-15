package dev.trove.core.network

import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

fun interface TroveApiFactory {
    fun create(baseUrl: String, token: String?): TroveApi
}

class RetrofitTroveApiFactory : TroveApiFactory {
    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
    }

    override fun create(baseUrl: String, token: String?): TroveApi {
        val client = TroveHttpClients.create(token)
        return Retrofit.Builder()
            .baseUrl(baseUrl.trimEnd('/') + "/")
            .client(client)
            .addConverterFactory(
                json.asConverterFactory("application/json".toMediaType())
            )
            .build()
            .create(TroveApi::class.java)
    }
}
