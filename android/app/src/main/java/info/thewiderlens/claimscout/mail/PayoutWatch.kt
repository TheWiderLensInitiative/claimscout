package info.thewiderlens.claimscout.mail

import info.thewiderlens.claimscout.data.Api
import info.thewiderlens.claimscout.data.MailAccount
import info.thewiderlens.claimscout.data.MailMessage
import info.thewiderlens.claimscout.data.Payout
import info.thewiderlens.claimscout.data.Store

/**
 * Looks through every connected inbox, Spam/Junk included, for settlement payout emails: virtual cards,
 * "choose your payment" links, PayPal/Venmo payments, checks, requests for more information.
 * The PC supplies the search (administrator senders + phrases) and works out what each email is.
 */
class PayoutWatch(private val store: Store, private val api: Api) {
    data class Result(val new: List<Payout>, val searched: Int, val errors: List<String>)

    suspend fun run(): Result {
        val accounts = store.accounts()
        if (accounts.isEmpty()) return Result(emptyList(), 0, emptyList())
        val plan = api.payoutPlan(store.payoutCheck())
        val limit = if (plan.first_run) 40 else 20
        val found = mutableListOf<MailMessage>()
        val errors = mutableListOf<String>()
        for (a in accounts) {
            var current: MailAccount = a
            try {
                for (q in queries(a.kind, plan.senders, plan.phrases, plan.after)) {
                    found += when (a.kind) {
                        "gmail" -> Gmail.search(a, q, limit, withSpam = true)
                        else -> Outlook.search(current, q, limit, withJunk = true).let { (m, updated) -> current = updated; m }
                    }
                }
            } catch (e: Exception) {
                errors += "${a.address}: ${e.message}"
            }
            if (current != a) store.saveAccount(current)
        }
        val unique = found.distinctBy { it.account to it.id }
        val new = unique.chunked(25).flatMap { api.payoutScan(it) }
        if (errors.isEmpty()) store.setPayoutCheck(System.currentTimeMillis() / 1000.0)
        return Result(new, unique.size, errors)
    }

    /** A few searches: administrator senders in groups (search length limits), then payout phrases. */
    private fun queries(kind: String, senders: List<String>, phrases: List<String>, after: String): List<String> {
        val day = if (kind == "gmail") " after:" + after.replace('-', '/') else " AND received>=$after"
        return if (kind == "gmail") {
            senders.chunked(25).map { g -> g.joinToString(" ", "{", "}") { "from:$it" } + day } +
                (phrases.joinToString(" ", "{", "}") { "\"$it\"" } + day)
        } else {
            senders.chunked(12).map { g -> g.joinToString(" OR ", "(", ")") { "from:$it" } + day } +
                (phrases.joinToString(" OR ", "(", ")") { "\"$it\"".replace("\"", "") .let { p -> "($p)" } } + day)
        }
    }
}
