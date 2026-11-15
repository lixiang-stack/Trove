package dev.trove.core.network

import java.util.concurrent.TimeUnit
import okhttp3.OkHttpClient

object TroveHttpClients {
    fun create(token: String?, readTimeoutSeconds: Long = 30): OkHttpClient =
        OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(readTimeoutSeconds, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val request = chain.request().newBuilder()
                    .header("User-Agent", "Trove-Android")
                    .apply {
                        if (token != null) {
                            header("Authorization", "Bearer $token")
                        }
                    }
                    .build()
                chain.proceed(request)
            }
            .build()
}
