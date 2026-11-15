package dev.trove.core.auth

data class StoredCredential(
    val token: String,
    val deviceId: String,
    val deviceName: String,
)

interface TokenStore {
    suspend fun read(): StoredCredential?

    suspend fun save(credential: StoredCredential)

    suspend fun clear()
}
