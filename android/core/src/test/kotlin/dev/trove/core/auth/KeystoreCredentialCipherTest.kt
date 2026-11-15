package dev.trove.core.auth

import android.security.keystore.KeyGenParameterSpec
import java.security.Key
import java.security.KeyStoreSpi
import java.security.Provider
import java.security.SecureRandom
import java.security.Security
import java.security.cert.Certificate
import java.security.spec.AlgorithmParameterSpec
import java.util.Collections
import java.util.Date
import javax.crypto.KeyGenerator
import javax.crypto.KeyGeneratorSpi
import javax.crypto.SecretKey
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.BeforeClass
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Robolectric has android.security.keystore classes but no AndroidKeyStore JCA
 * provider. This test-scoped provider lets the real KeystoreCredentialCipher
 * exercise its KeyStore/KeyGenerator/Cipher path without device hardware.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [36])
class KeystoreCredentialCipherTest {
    @Test
    fun encryptionRoundTripsAndDoesNotStorePlaintext() {
        val cipher = KeystoreCredentialCipher()
        val plaintext = "secret-token-value".encodeToByteArray()

        val encrypted = cipher.encrypt(plaintext)

        assertFalse(encrypted.ciphertext.contentEquals(plaintext))
        assertTrue(encrypted.iv.size in 12..16)
        assertArrayEquals(plaintext, cipher.decrypt(encrypted.ciphertext, encrypted.iv))
    }

    @Test
    fun eachEncryptionUsesAFreshIv() {
        val cipher = KeystoreCredentialCipher()
        val first = cipher.encrypt("a".encodeToByteArray())
        val second = cipher.encrypt("a".encodeToByteArray())
        assertFalse(first.iv.contentEquals(second.iv))
    }

    companion object {
        @BeforeClass
        @JvmStatic
        fun installProvider() {
            if (Security.getProvider(ANDROID_KEYSTORE) == null) {
                Security.addProvider(TestAndroidKeyStoreProvider())
            }
        }

        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    }
}

private class TestAndroidKeyStoreProvider : Provider(ANDROID_KEYSTORE, 1.0, "Robolectric") {
    init {
        put("KeyStore.AndroidKeyStore", TestKeyStoreSpi::class.java.name)
        put("KeyGenerator.AES", TestAesKeyGeneratorSpi::class.java.name)
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
    }
}

private object TestKeyStoreData {
    val keys = mutableMapOf<String, Key>()
}

class TestKeyStoreSpi : KeyStoreSpi() {
    override fun engineGetKey(alias: String?, password: CharArray?): Key? =
        alias?.let { TestKeyStoreData.keys[it] }

    override fun engineGetCertificateChain(alias: String?): Array<Certificate>? = null

    override fun engineGetCertificate(alias: String?): Certificate? = null

    override fun engineGetCreationDate(alias: String?): Date = Date()

    override fun engineSetKeyEntry(
        alias: String?,
        key: Key?,
        password: CharArray?,
        chain: Array<out Certificate>?,
    ) {
        if (alias != null && key != null) {
            TestKeyStoreData.keys[alias] = key
        }
    }

    override fun engineSetKeyEntry(
        alias: String?,
        key: ByteArray?,
        chain: Array<out Certificate>?,
    ) = Unit

    override fun engineSetCertificateEntry(alias: String?, cert: Certificate?) = Unit

    override fun engineDeleteEntry(alias: String?) {
        alias?.let { TestKeyStoreData.keys.remove(it) }
    }

    override fun engineAliases(): java.util.Enumeration<String> =
        Collections.enumeration(TestKeyStoreData.keys.keys)

    override fun engineContainsAlias(alias: String?): Boolean =
        alias != null && alias in TestKeyStoreData.keys

    override fun engineSize(): Int = TestKeyStoreData.keys.size

    override fun engineIsKeyEntry(alias: String?): Boolean =
        alias != null && alias in TestKeyStoreData.keys

    override fun engineIsCertificateEntry(alias: String?): Boolean = false

    override fun engineGetCertificateAlias(cert: Certificate?): String? = null

    override fun engineStore(stream: java.io.OutputStream?, password: CharArray?) = Unit

    override fun engineLoad(stream: java.io.InputStream?, password: CharArray?) = Unit
}

class TestAesKeyGeneratorSpi : KeyGeneratorSpi() {
    private var alias: String? = null

    override fun engineInit(random: SecureRandom?) = Unit

    override fun engineInit(params: AlgorithmParameterSpec?, random: SecureRandom?) {
        alias = (params as? KeyGenParameterSpec)?.keystoreAlias
    }

    override fun engineInit(keysize: Int, random: SecureRandom?) = Unit

    override fun engineGenerateKey(): SecretKey {
        val key = KeyGenerator.getInstance("AES")
            .apply { init(256) }
            .generateKey()
        alias?.let { TestKeyStoreData.keys[it] = key }
        return key
    }
}
