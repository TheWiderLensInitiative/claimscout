package info.thewiderlens.claimscout.mail

import android.net.Uri
import info.thewiderlens.claimscout.data.MailAccount
import info.thewiderlens.claimscout.data.MailMessage
import info.thewiderlens.claimscout.data.json
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/**
 * Outlook / Hotmail / Microsoft 365 through Microsoft Graph, read-only (Mail.Read).
 * Sign-in is the device-code flow: the app shows a short code, the user enters it at microsoft.com/link.
 * No redirect URI or client secret, so any public-client app registration works.
 */
object Outlook {
    private const val LOGIN = "https://login.microsoftonline.com/common/oauth2/v2.0"
    private const val SCOPES = "offline_access User.Read Mail.Read"
    private val http = OkHttpClient.Builder().readTimeout(60, TimeUnit.SECONDS).build()

    data class DeviceCode(val userCode: String, val verifyUrl: String, val deviceCode: String, val interval: Int, val expiresIn: Int)

    private fun post(url: String, form: Map<String, String>): JsonObject {
        val body = FormBody.Builder().apply { form.forEach { (k, v) -> add(k, v) } }.build()
        http.newCall(Request.Builder().url(url).post(body).build()).execute().use { r ->
            return json.decodeFromString<JsonObject>(r.body.string())
        }
    }

    private fun JsonObject.str(k: String) = this[k]?.jsonPrimitive?.content

    suspend fun start(clientId: String): DeviceCode = withContext(Dispatchers.IO) {
        val d = post("$LOGIN/devicecode", mapOf("client_id" to clientId, "scope" to SCOPES))
        val code = d.str("user_code") ?: throw IllegalStateException(d.str("error_description")?.lineSequence()?.first() ?: "Microsoft refused the sign-in")
        DeviceCode(code, d.str("verification_uri") ?: "https://microsoft.com/link", d.str("device_code")!!,
            d["interval"]?.jsonPrimitive?.int ?: 5, d["expires_in"]?.jsonPrimitive?.int ?: 900)
    }

    /** Waits until the user has entered the code. Returns the connected account. */
    suspend fun finish(clientId: String, dc: DeviceCode): MailAccount = withContext(Dispatchers.IO) {
        var interval = dc.interval
        val until = System.currentTimeMillis() + dc.expiresIn * 1000L
        while (System.currentTimeMillis() < until) {
            delay(interval * 1000L)
            val t = post("$LOGIN/token", mapOf("client_id" to clientId, "device_code" to dc.deviceCode,
                "grant_type" to "urn:ietf:params:oauth:grant-type:device_code"))
            val access = t.str("access_token")
            if (access != null) {
                val me = get("https://graph.microsoft.com/v1.0/me?\$select=mail,userPrincipalName", access)
                val address = me.str("mail") ?: me.str("userPrincipalName") ?: "Outlook"
                return@withContext MailAccount("outlook", address, t.str("refresh_token") ?: error("no refresh token"), clientId)
            }
            when (t.str("error")) {
                "authorization_pending" -> {}
                "slow_down" -> interval += 5
                "authorization_declined" -> error("You declined the sign-in.")
                "expired_token" -> error("The code expired. Try again.")
                else -> error(t.str("error_description")?.lineSequence()?.first() ?: "Sign-in failed")
            }
        }
        error("The code expired. Try again.")
    }

    private fun get(url: String, token: String): JsonObject =
        http.newCall(Request.Builder().url(url).header("Authorization", "Bearer $token")
            .header("Prefer", "outlook.body-content-type=\"text\"").build()).execute().use { r ->
            val o = json.decodeFromString<JsonObject>(r.body.string())
            if (!r.isSuccessful) error(o["error"]?.jsonObject?.str("message") ?: "Outlook said ${r.code}")
            o
        }

    /** A fresh access token. Microsoft may rotate the refresh token; the caller saves the returned account. */
    private fun access(a: MailAccount): Pair<String, MailAccount> {
        val t = post("$LOGIN/token", mapOf("client_id" to (a.clientId ?: ""), "grant_type" to "refresh_token",
            "refresh_token" to a.secret, "scope" to SCOPES))
        val access = t.str("access_token") ?: error("Outlook sign-in expired for ${a.address}. Reconnect it.")
        return access to a.copy(secret = t.str("refresh_token") ?: a.secret)
    }

    /** Search all mail, plus the Junk folder when withJunk (payout emails often land there). */
    suspend fun search(a: MailAccount, query: String, limit: Int, withJunk: Boolean = false): Pair<List<MailMessage>, MailAccount> =
        withContext(Dispatchers.IO) {
            val (token, updated) = access(a)
            val places = listOf("me/messages" to "") + if (withJunk) listOf("me/mailFolders/junkemail/messages" to "junk") else emptyList()
            places.flatMap { (path, folder) ->
                val url = "https://graph.microsoft.com/v1.0/$path?\$search=" + Uri.encode("\"$query\"") +
                    "&\$top=$limit&\$select=id,subject,from,receivedDateTime,body,webLink"
                (get(url, token)["value"]?.jsonArray ?: return@flatMap emptyList()).map { it.jsonObject }.map { m ->
                    val from = m["from"]?.jsonObject?.get("emailAddress")?.jsonObject
                    MailMessage(account = a.address, id = "outlook:" + m.str("id"),
                        from = listOfNotNull(from?.str("name"), from?.str("address")?.let { "<$it>" }).joinToString(" "),
                        subject = m.str("subject") ?: "", date = m.str("receivedDateTime")?.take(10) ?: "",
                        text = MailText.clean(m["body"]?.jsonObject?.str("content") ?: "").take(MailText.MAX),
                        link = m.str("webLink") ?: "", folder = folder)
                }
            }.distinctBy { it.id } to updated
        }

    /** KQL for Graph's $search. Phrases can't be quoted inside the outer quotes, so each keyword is grouped. */
    fun query(senders: List<String>, keywords: List<String>, after: String?, before: String?): String {
        val clean = { s: String -> s.replace(Regex("[\"()]"), " ").trim() }
        val parts = mutableListOf<String>()
        if (senders.isNotEmpty()) parts += senders.joinToString(" OR ", "(", ")") { "from:${clean(it)}" }
        if (keywords.isNotEmpty()) parts += keywords.joinToString(" OR ", "(", ")") { "(${clean(it)})" }
        after?.let { parts += "received>=$it" }
        before?.let { parts += "received<=$it" }
        return parts.joinToString(" AND ")
    }
}
