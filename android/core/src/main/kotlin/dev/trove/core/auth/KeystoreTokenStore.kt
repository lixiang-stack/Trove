package dev.trove.core.auth

import android.content.Context
import android.util.Base64
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import dev.trove.core.storage.tokenDataStore
import java.security.GeneralSecurityException
import kotlinx.coroutines.flow.first
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

private val CIPHERTEXT_KEY = stringPreferencesKey("credential_ciphertext")
private val IV_KEY = stringPreferencesKey("credential_iv")

@Serializable
private data class CredentialPayload(
    val token: String,
    val deviceId: String,
    val deviceName: String,
)

class KeystoreTokenStore(
    context: Context,
    private val dataStore: DataStore<Preferences> = context.tokenDataStore,
    private val cipher: CredentialCipher = KeystoreCredentialCipher(),
) : TokenStore {
    private val json = Json { ignoreUnknownKeys = true }

    override suspend fun read(): StoredCredential? {
        val preferences = dataStore.data.first()
        val ciphertext = preferences[CIPHERTEXT_KEY] ?: return null
        val iv = preferences[IV_KEY] ?: return null
        return try {
            val plaintext = cipher.decrypt(
                Base64.decode(ciphertext, Base64.NO_WRAP),
                Base64.decode(iv, Base64.NO_WRAP),
            )
            val payload = json.decodeFromString<CredentialPayload>(
                plaintext.decodeToString()
            )
            StoredCredential(payload.token, payload.deviceId, payload.deviceName)
        } catch (_: GeneralSecurityException) {
            null
        } catch (_: IllegalArgumentException) {
            null
        } catch (_: kotlinx.serialization.SerializationException) {
            null
        }
    }

    override suspend fun save(credential: StoredCredential) {
        val plaintext = json.encodeToString(
            CredentialPayload(
                token = credential.token,
                deviceId = credential.deviceId,
                deviceName = credential.deviceName,
            )
        ).encodeToByteArray()
        val encrypted = cipher.encrypt(plaintext)
        require(encrypted.iv.size in 12..16) { "Unexpected GCM IV length" }
        dataStore.edit { preferences ->
            preferences[CIPHERTEXT_KEY] = Base64.encodeToString(
                encrypted.ciphertext,
                Base64.NO_WRAP,
            )
            preferences[IV_KEY] = Base64.encodeToString(encrypted.iv, Base64.NO_WRAP)
        }
    }

    override suspend fun clear() {
        dataStore.edit { preferences ->
            preferences.remove(CIPHERTEXT_KEY)
            preferences.remove(IV_KEY)
        }
    }
}
