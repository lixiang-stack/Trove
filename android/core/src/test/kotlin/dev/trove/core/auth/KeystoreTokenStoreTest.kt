package dev.trove.core.auth

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.test.core.app.ApplicationProvider
import dev.trove.core.storage.tokenDataStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

private class JvmCredentialCipher : CredentialCipher {
    private val key: SecretKey =
        KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()

    override fun encrypt(plaintext: ByteArray): EncryptedCredential {
        val iv = ByteArray(12).also { SecureRandom().nextBytes(it) }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key, GCMParameterSpec(128, iv))
        return EncryptedCredential(cipher.doFinal(plaintext), iv)
    }

    override fun decrypt(ciphertext: ByteArray, iv: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, iv))
        return cipher.doFinal(ciphertext)
    }
}

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class KeystoreTokenStoreTest {
    @Test
    fun credentialRoundTripsAndIsNotStoredInPlaintext() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val store = KeystoreTokenStore(context, cipher = JvmCredentialCipher())
        store.clear()

        val credential = StoredCredential(
            token = "secret-token-value",
            deviceId = "device-1",
            deviceName = "Pixel",
        )
        store.save(credential)
        assertEquals(credential, store.read())

        val preferences = context.tokenDataStore.data.first()
        assertFalse(preferences.asMap().values.any { it.toString().contains("secret-token") })

        store.clear()
        assertNull(store.read())
    }

    @Test
    fun corruptedCiphertextIsTreatedAsSignedOut() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val store = KeystoreTokenStore(context, cipher = JvmCredentialCipher())
        store.clear()
        store.save(StoredCredential("secret-token-value", "device-1", "Pixel"))
        context.tokenDataStore.edit { preferences ->
            preferences[
                androidx.datastore.preferences.core.stringPreferencesKey("credential_iv")
            ] = "not-base64"
        }
        assertNull(store.read())
    }
}
