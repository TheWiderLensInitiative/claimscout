package info.thewiderlens.claimscout.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

private val Context.dataStore by preferencesDataStore("claimscout")

/** Where the PC is and how to trust it. */
@Serializable
data class Pairing(val urls: List<String>, val token: String, val fingerprint: String, val lastGood: String? = null)

/** An email account connected on this phone. The secret is an app password (Gmail) or a refresh token (Outlook). */
@Serializable
data class MailAccount(val kind: String, val address: String, val secret: String, val clientId: String? = null)

val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

class Store(private val ctx: Context) {
    private val pairingKey = stringPreferencesKey("pairing")
    private val accountsKey = stringPreferencesKey("accounts")
    private val notifiedKey = stringPreferencesKey("notified")
    private val msClientKey = stringPreferencesKey("ms_client_id")
    private val onboardedKey = stringPreferencesKey("onboarded")

    /** Set once the first-run questionnaire is finished (or skipped) on this phone. */
    val onboardedFlow = ctx.dataStore.data.map { it[onboardedKey] == "1" }
    suspend fun setOnboarded(done: Boolean) = ctx.dataStore.edit { it[onboardedKey] = if (done) "1" else "0" }

    val pairingFlow = ctx.dataStore.data.map { p -> p[pairingKey]?.let { Sealed.open(it) }?.let { json.decodeFromString<Pairing>(it) } }
    val accountsFlow = ctx.dataStore.data.map { p ->
        p[accountsKey]?.let { Sealed.open(it) }?.let { json.decodeFromString<List<MailAccount>>(it) } ?: emptyList()
    }

    suspend fun pairing(): Pairing? = pairingFlow.first()
    suspend fun setPairing(p: Pairing?) = ctx.dataStore.edit {
        if (p == null) { it.remove(pairingKey); it.remove(onboardedKey) } else it[pairingKey] = Sealed.seal(json.encodeToString(p))
    }

    suspend fun accounts(): List<MailAccount> = accountsFlow.first()
    suspend fun saveAccount(a: MailAccount) = setAccounts(accounts().filterNot { it.kind == a.kind && it.address == a.address } + a)
    suspend fun removeAccount(a: MailAccount) = setAccounts(accounts().filterNot { it.kind == a.kind && it.address == a.address })
    private suspend fun setAccounts(list: List<MailAccount>) = ctx.dataStore.edit { it[accountsKey] = Sealed.seal(json.encodeToString(list)) }

    suspend fun notified(): Set<String> = ctx.dataStore.data.first()[notifiedKey]?.split('\n')?.filter { it.isNotEmpty() }?.toSet() ?: emptySet()
    suspend fun addNotified(ids: Collection<String>) = ctx.dataStore.edit {
        it[notifiedKey] = ((it[notifiedKey]?.split('\n') ?: emptyList()) + ids).filter { s -> s.isNotEmpty() }.takeLast(2000).joinToString("\n")
    }

    suspend fun msClientId(): String = ctx.dataStore.data.first()[msClientKey] ?: ""
    suspend fun setMsClientId(id: String) = ctx.dataStore.edit { it[msClientKey] = id.trim() }
}

/** AES-GCM with a key held in the Android Keystore: secrets on disk are useless off this phone. */
object Sealed {
    private const val ALIAS = "claimscout-store"

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build())
        }.generateKey()
    }

    fun seal(plain: String): String {
        val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        return Base64.encodeToString(c.iv + c.doFinal(plain.toByteArray()), Base64.NO_WRAP)
    }

    fun open(sealed: String): String? = runCatching {
        val all = Base64.decode(sealed, Base64.NO_WRAP)
        val c = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, all, 0, 12))
        }
        String(c.doFinal(all, 12, all.size - 12))
    }.getOrNull()
}
