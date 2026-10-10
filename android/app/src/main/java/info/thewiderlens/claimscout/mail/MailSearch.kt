package info.thewiderlens.claimscout.mail

import info.thewiderlens.claimscout.data.MailAccount
import info.thewiderlens.claimscout.data.MailMessage
import info.thewiderlens.claimscout.data.Plan
import info.thewiderlens.claimscout.data.Store

/**
 * Runs a settlement's proof plan against every connected inbox, on the phone. Starts strict (sender AND
 * keywords AND dates) and loosens until something turns up. Only the matches go to the PC.
 */
class MailSearch(private val store: Store) {
    data class Result(val messages: List<MailMessage>, val searched: List<String>, val errors: List<String>)

    private fun attempts(p: Plan): List<Plan> = listOf(
        p,
        p.copy(after = null, before = null),
        p.copy(keywords = emptyList()),
        p.copy(senders = emptyList(), after = null, before = null),
    ).filter { it.senders.isNotEmpty() || it.keywords.isNotEmpty() }.distinct()

    suspend fun run(plan: Plan, limit: Int = 15): Result {
        val found = mutableListOf<MailMessage>()
        val searched = mutableListOf<String>()
        val errors = mutableListOf<String>()
        for (a in store.accounts()) {
            searched += a.address
            var current: MailAccount = a
            var lastError: String? = null
            for (p in attempts(plan)) {
                try {
                    val hits = when (a.kind) {
                        "gmail" -> Gmail.search(a, Gmail.query(p.senders, p.keywords, p.after, p.before), limit)
                        "outlook" -> Outlook.search(current, Outlook.query(p.senders, p.keywords, p.after, p.before), limit)
                            .let { (msgs, updated) -> current = updated; msgs }
                        else -> emptyList()
                    }
                    if (hits.isNotEmpty()) { found += hits; lastError = null; break }
                } catch (e: Exception) {
                    lastError = "${a.address}: ${e.message}"   // a looser query may still work (e.g. Graph rejects a date)
                }
            }
            lastError?.let { errors += it }
            if (current != a) store.saveAccount(current)   // Microsoft rotated the refresh token
        }
        return Result(found.distinctBy { it.account to it.id }.take(limit), searched, errors.distinct())
    }
}
