package dev.trove.core.network

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface TroveApi {
    @GET("api/health")
    suspend fun health(): HealthDto

    @POST("api/auth/device-token")
    suspend fun deviceToken(@Body request: DeviceTokenRequest): DeviceTokenResponse

    @GET("api/devices")
    suspend fun devices(): DeviceListResponse

    @DELETE("api/devices/{deviceId}")
    suspend fun revokeDevice(@Path("deviceId") deviceId: String): Response<Unit>

    @GET("api/sync/manifest")
    suspend fun manifest(
        @Query("cursor") cursor: String?,
        @Query("limit") limit: Int,
    ): ManifestDto

    @GET("api/sync/state")
    suspend fun state(
        @Query("cursor") cursor: String?,
        @Query("limit") limit: Int,
    ): SyncStateDto
}
