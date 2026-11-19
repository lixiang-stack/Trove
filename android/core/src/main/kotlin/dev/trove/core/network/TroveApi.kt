package dev.trove.core.network

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.PUT
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

    @PUT("api/items/{itemId}/progress")
    suspend fun progress(
        @Path("itemId") itemId: String,
        @Body body: ProgressRequestDto,
        @Header("Idempotency-Key") idempotencyKey: String?,
    ): MutationResponseDto

    @PUT("api/items/{itemId}/tags")
    suspend fun tags(
        @Path("itemId") itemId: String,
        @Body body: TagsRequestDto,
        @Header("Idempotency-Key") idempotencyKey: String?,
    ): MutationResponseDto

    @POST("api/items")
    suspend fun createItem(@Body body: ItemCreateRequestDto): ItemCreateResponseDto

    @GET("api/items/{itemId}")
    suspend fun item(@Path("itemId") itemId: String): ItemDto

    @GET("api/items/{itemId}/transcript")
    suspend fun transcript(@Path("itemId") itemId: String): TranscriptResponseDto

    @POST("api/items/{itemId}/retry")
    suspend fun retryItem(@Path("itemId") itemId: String): ItemDto

    @POST("api/intake/inspect")
    suspend fun inspectLink(@Body body: LinkInspectRequestDto): LinkInspectResponseDto

    @POST("api/collections")
    suspend fun createCollection(@Body body: CollectionCreateRequestDto): CollectionCreateResponseDto

    @GET("api/collections/{collectionId}")
    suspend fun collection(@Path("collectionId") collectionId: String): CollectionDto

    @DELETE("api/collections/{collectionId}")
    suspend fun deleteCollection(
        @Path("collectionId") collectionId: String,
        @Query("mode") mode: String,
    ): CollectionDeleteResponseDto

    @POST("api/collections/{collectionId}/retry-failed")
    suspend fun retryCollectionFailed(@Path("collectionId") collectionId: String): CollectionDto

    @GET("api/collections")
    suspend fun collections(): CollectionListResponseDto

    @POST("api/feeds/preview")
    suspend fun previewFeed(@Body body: FeedPreviewRequestDto): FeedPreviewResponseDto

    @GET("api/search")
    suspend fun search(
        @Query("q") query: String,
        @Query("type") type: String?,
        @Query("consumption") consumption: String?,
        @Query("tag") tag: String?,
        @Query("source") source: String?,
        @Query("limit") limit: Int,
    ): SearchResponseDto

    @DELETE("api/items/{itemId}")
    suspend fun deleteItem(@Path("itemId") itemId: String): Response<Unit>
}
