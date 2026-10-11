package info.thewiderlens.claimscout.data

import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.JsonObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

@Serializable data class Plan(val senders: List<String> = emptyList(), val keywords: List<String> = emptyList(),
                              val after: String? = null, val before: String? = null)
@Serializable data class Row(val id: String, val title: String, val award: String? = null, val deadline: String? = null,
                             val proof_needed: Int? = null, val states: List<String> = emptyList(), val source: String? = null,
                             val verdict: String? = null, val reason: String? = null, val claim_status: String? = null, val proofs: Int = 0,
                             val label: String? = null, val category: String? = null, val logo: Boolean = false, val amount: Double? = null)
@Serializable data class Rows(val settlements: List<Row>)
@Serializable data class Match(val verdict: String? = null, val reason: String? = null, val method: String? = null)
@Serializable data class Proof(val id: Long? = null, val account: String? = null, val message_id: String? = null,
                               val sender: String? = null, val subject: String? = null, val date: String? = null,
                               val kind: String? = null, val amount: String? = null, val order_number: String? = null,
                               val summary: String? = null)
@Serializable data class Proofs(val proofs: List<Proof>)
@Serializable data class Claim(val status: String = "filed", val claim_number: String? = null, val filed_at: String? = null,
                               val expected: String? = null, val paid: String? = null, val notes: String? = null)
@Serializable data class Detail(val id: String, val title: String, val url: String? = null, val summary: String? = null,
                                val eligibility: String? = null, val award: String? = null, val proof: String? = null,
                                val proof_needed: Int? = null, val claim_url: String? = null, val website: String? = null,
                                val deadline: String? = null, val case_name: String? = null, val states: List<String> = emptyList(),
                                val source: String? = null, val match: Match? = null, val proof_plan: Plan? = null,
                                val claim: Claim? = null, val proofs: List<Proof> = emptyList(),
                                val label: String? = null, val category: String? = null, val logo: Boolean = false, val amount: Double? = null)
@Serializable data class Status(val version: String, val open: Int, val likely: Int, val maybe: Int, val claims: Int,
                                val refreshing: Boolean = false, val profile_set: Boolean = false, val unanswered: Int = 0,
                                val potential: Int = 0, val potential_unknown: Int = 0, val money_waiting: Int = 0)
@Serializable data class QItem(val id: String, val label: String, val title: String, val question: String? = null,
                               val eligibility: String? = null, val states: List<String> = emptyList(),
                               val deadline: String? = null, val award: String? = null, val proof_needed: Int? = null,
                               val answer: String? = null, val logo: Boolean = false)
@Serializable data class QGroup(val category: String, val prompt: String, val items: List<QItem>)
@Serializable data class Questionnaire(val states_known: Boolean = false, val groups: List<QGroup> = emptyList(),
                                       val count: Int = 0, val skipped_by_state: Int = 0, val answered: Int = 0)
@Serializable data class AnswersBody(val answers: Map<String, String>, val used: List<String> = emptyList())
@Serializable data class AnswersReply(val saved: Int, val status: Status)
@Serializable data class Profile(val name: String = "", val states: List<String> = emptyList(),
                                 val past_states: List<String> = emptyList(), val companies: List<String> = emptyList(),
                                 val about: String = "")
@Serializable data class NewItem(val id: String, val title: String, val deadline: String? = null, val award: String? = null)
@Serializable data class NewItems(val new: List<NewItem>, val now: Double)
@Serializable data class MailMessage(val account: String, val id: String, val from: String, val subject: String,
                                     val date: String, val text: String, val link: String = "", val folder: String = "")
@Serializable data class PayoutPlan(val senders: List<String>, val phrases: List<String>, val after: String, val first_run: Boolean = false)
@Serializable data class Payout(val id: Long, val account: String? = null, val link: String? = null, val sender: String? = null,
                                val subject: String? = null, val date: String? = null, val folder: String? = null,
                                val kind: String, val label: String = "", val settlement: String? = null, val amount: String? = null,
                                val expires: String? = null, val action: String? = null, val status: String = "new",
                                val needs_action: Boolean = false)
@Serializable data class Payouts(val payouts: List<Payout> = emptyList(), val new: List<Payout> = emptyList())
@Serializable data class ScanBody(val messages: List<MailMessage>)
@Serializable data class ProofRequest(val messages: List<MailMessage>)

class ApiException(msg: String, val code: Int = 0) : IOException(msg)

/** Parse claimscout://pair?u=https://192.168.1.5:8787&u=https://100.x.y.z:8787&t=TOKEN&f=FINGERPRINT */
fun parsePairLink(link: String): Pairing? {
    val uri = Uri.parse(link.trim())
    if (uri.scheme != "claimscout" || uri.host != "pair") return null
    val urls = uri.getQueryParameters("u").filter { it.startsWith("https://") }
    val t = uri.getQueryParameter("t") ?: return null
    val f = uri.getQueryParameter("f")?.lowercase()?.takeIf { it.matches(Regex("[0-9a-f]{64}")) } ?: return null
    return if (urls.isEmpty()) null else Pairing(urls, t, f)
}

/**
 * Talks to the PC. Trusts exactly one certificate (the PC's self-signed one, by SHA-256), so the
 * hostname doesn't matter and nobody else on the network can pose as the PC or read the traffic.
 */
class Api(private val pairing: Pairing, private val onGood: suspend (String) -> Unit = {}) {
    private val trust = object : X509TrustManager {
        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) = throw CertificateException()
        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
            val fp = MessageDigest.getInstance("SHA-256").digest(chain[0].encoded).joinToString("") { "%02x".format(it) }
            if (fp != pairing.fingerprint) throw CertificateException("not your ClaimScout PC")
        }
        override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
    }
    private val http = OkHttpClient.Builder()
        .sslSocketFactory(SSLContext.getInstance("TLS").apply { init(null, arrayOf(trust), null) }.socketFactory, trust)
        .hostnameVerifier { _, _ -> true }   // safe only because of the pin above
        .connectTimeout(4, TimeUnit.SECONDS)
        .readTimeout(240, TimeUnit.SECONDS)  // proof extraction on a local model can take a while
        .build()

    private suspend fun call(method: String, path: String, body: String? = null): String = withContext(Dispatchers.IO) {
        val order = listOfNotNull(pairing.lastGood) + pairing.urls.filter { it != pairing.lastGood }
        var last: IOException = ApiException("can't reach your PC")
        for (base in order) {
            val req = Request.Builder().url(base + "/api" + path)
                .header("Authorization", "Bearer ${pairing.token}")
                .method(method, body?.toRequestBody("application/json".toMediaType()))
                .build()
            try {
                http.newCall(req).execute().use { r ->
                    val text = r.body.string()
                    if (base != pairing.lastGood) onGood(base)
                    if (r.code == 401) throw ApiException("This phone isn't paired anymore. Pair again from the PC.", 401)
                    if (!r.isSuccessful) throw ApiException(errorDetail(text) ?: "PC said ${r.code}", r.code)
                    return@withContext text
                }
            } catch (e: ApiException) {
                throw e
            } catch (e: IOException) {
                last = if (e.cause is CertificateException || e.message?.contains("ClaimScout PC") == true)
                    ApiException("That isn't your ClaimScout PC (certificate changed). Pair again.") else e
            }
        }
        throw ApiException("Can't reach your PC. Is it on, and is this phone on the same Wi-Fi (or Tailscale)? " +
            "On the PC, run claimscout doctor to see what's wrong. (${last.message})")
    }

    /** A company logo PNG from the PC, or null if it has none. */
    suspend fun logo(id: String): ByteArray? = withContext(Dispatchers.IO) {
        val order = listOfNotNull(pairing.lastGood) + pairing.urls.filter { it != pairing.lastGood }
        for (base in order) {
            val req = Request.Builder().url("$base/api/logo/${Uri.encode(id)}").header("Authorization", "Bearer ${pairing.token}").build()
            try {
                http.newCall(req).execute().use { r -> return@withContext if (r.isSuccessful) r.body.bytes() else null }
            } catch (e: IOException) { continue }
        }
        null
    }

    private fun errorDetail(text: String) = runCatching { json.decodeFromString<JsonObject>(text)["detail"]?.toString()?.trim('"') }.getOrNull()

    suspend fun status() = json.decodeFromString<Status>(call("GET", "/status"))
    suspend fun settlements(view: String, q: String = "", category: String = "") =
        json.decodeFromString<Rows>(call("GET", "/settlements?view=$view&q=${Uri.encode(q)}&category=${Uri.encode(category)}")).settlements
    suspend fun detail(id: String) = json.decodeFromString<Detail>(call("GET", "/settlements/${Uri.encode(id)}"))
    suspend fun dismiss(id: String) = call("POST", "/settlements/${Uri.encode(id)}/dismiss", "{}")
    suspend fun rematch(id: String) = call("POST", "/settlements/${Uri.encode(id)}/match", "{}")
    suspend fun addProof(id: String, msgs: List<MailMessage>) =
        json.decodeFromString<Proofs>(call("POST", "/settlements/${Uri.encode(id)}/proof", json.encodeToString(ProofRequest(msgs)))).proofs
    suspend fun deleteProof(pid: Long) = call("DELETE", "/proofs/$pid", "{}")
    suspend fun saveClaim(id: String, c: Claim) = call("PUT", "/claims/${Uri.encode(id)}", json.encodeToString(c))
    suspend fun deleteClaim(id: String) = call("DELETE", "/claims/${Uri.encode(id)}", "{}")
    suspend fun profile() = json.decodeFromString<Profile>(call("GET", "/profile"))
    suspend fun saveProfile(p: Profile) = call("PUT", "/profile", json.encodeToString(p))
    suspend fun refresh() = call("POST", "/refresh", "{}")
    suspend fun questionnaire(all: Boolean = false) = json.decodeFromString<Questionnaire>(call("GET", "/questionnaire?all=$all"))
    suspend fun answer(answers: Map<String, String>, used: List<String> = emptyList()) =
        json.decodeFromString<AnswersReply>(call("POST", "/answers", json.encodeToString(AnswersBody(answers, used)))).status
    suspend fun resetAnswers() = call("DELETE", "/answers", "{}")
    suspend fun payoutPlan(since: Double?) =
        json.decodeFromString<PayoutPlan>(call("GET", "/payouts/plan" + (since?.let { "?since=$it" } ?: "")))
    suspend fun payoutScan(msgs: List<MailMessage>) =
        json.decodeFromString<Payouts>(call("POST", "/payouts/scan", json.encodeToString(ScanBody(msgs)))).new
    suspend fun payouts() = json.decodeFromString<Payouts>(call("GET", "/payouts")).payouts
    suspend fun payoutStatus(id: Long, status: String) = call("POST", "/payouts/$id", "{\"status\":\"$status\"}")
    suspend fun newSince(since: Double) = json.decodeFromString<NewItems>(call("GET", "/new?since=$since"))
}
