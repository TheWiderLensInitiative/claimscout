package info.thewiderlens.claimscout.mail

import com.sun.mail.iap.Argument
import com.sun.mail.imap.IMAPFolder
import com.sun.mail.imap.protocol.IMAPResponse
import android.net.Uri
import info.thewiderlens.claimscout.data.MailAccount
import info.thewiderlens.claimscout.data.MailMessage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.Properties
import javax.mail.FetchProfile
import javax.mail.Folder
import javax.mail.Session
import javax.mail.Store

/**
 * Gmail over IMAP with an app password (Google Account → Security → 2-Step Verification → App passwords).
 * Searches with Gmail's own syntax (X-GM-RAW), the same as the Gmail search box, read-only.
 */
object Gmail {
    private fun connect(address: String, appPassword: String): Store {
        val props = Properties().apply {
            put("mail.imaps.host", "imap.gmail.com")
            put("mail.imaps.port", "993")
            put("mail.imaps.ssl.checkserveridentity", "true")
            put("mail.imaps.connectiontimeout", "15000")
            put("mail.imaps.timeout", "30000")
        }
        return Session.getInstance(props).getStore("imaps").apply {
            connect("imap.gmail.com", address, appPassword.replace(" ", ""))
        }
    }

    /** Throws with a readable message if the address/app password don't work. */
    suspend fun verify(address: String, appPassword: String) = withContext(Dispatchers.IO) {
        try {
            connect(address, appPassword).close()
        } catch (e: javax.mail.AuthenticationFailedException) {
            throw IllegalArgumentException("Gmail didn't accept that. Use an app password (16 letters), not your normal password.")
        }
    }

    /** "[Gmail]/All Mail" and "[Gmail]/Spam" have other names in other languages; find them by their flags. */
    private fun special(store: Store, flag: String): Folder? =
        store.defaultFolder.list("*").firstOrNull { (it as? IMAPFolder)?.attributes?.contains(flag) == true }

    /** Search All Mail (and Spam when withSpam: Gmail's IMAP search never looks in Spam from All Mail). */
    suspend fun search(account: MailAccount, query: String, limit: Int, withSpam: Boolean = false): List<MailMessage> =
        withContext(Dispatchers.IO) {
            val store = connect(account.address, account.secret)
            try {
                val folders = listOfNotNull(special(store, "\\All") ?: store.getFolder("INBOX"),
                    if (withSpam) special(store, "\\Junk") else null)
                folders.flatMap { searchFolder(account, it as IMAPFolder, query, limit, isSpam = it != folders.first()) }
            } finally {
                store.close()
            }
        }

    private fun searchFolder(account: MailAccount, folder: IMAPFolder, query: String, limit: Int, isSpam: Boolean): List<MailMessage> {
        run {
            folder.open(Folder.READ_ONLY)
            @Suppress("UNCHECKED_CAST")
            val nums = folder.doCommand { p ->
                val args = Argument().apply { writeString(query.filter { it.code in 32..126 }) }
                val rs = p.command("SEARCH X-GM-RAW", args)
                val out = mutableListOf<Int>()
                rs.filterIsInstance<IMAPResponse>().filter { it.keyEquals("SEARCH") }.forEach { r ->
                    while (true) { val n = r.readNumber(); if (n == -1) break; out += n }
                }
                p.handleResult(rs.last())
                out
            } as List<Int>
            val msgs = folder.getMessages(nums.sorted().takeLast(limit).reversed().toIntArray())
            folder.fetch(msgs, FetchProfile().apply { add(FetchProfile.Item.ENVELOPE); add("Message-ID") })
            val day = SimpleDateFormat("yyyy-MM-dd", Locale.US)
            return msgs.map { m ->
                val msgId = m.getHeader("Message-ID")?.firstOrNull()?.trim()?.trim('<', '>')
                MailMessage(account = account.address, id = "gmail:" + (msgId ?: (if (isSpam) "spam:" else "") + folder.getUID(m)),
                    from = m.from?.firstOrNull()?.toString() ?: "", subject = m.subject ?: "",
                    date = (m.receivedDate ?: m.sentDate)?.let { day.format(it) } ?: "",
                    text = MailText.of(m), folder = if (isSpam) "spam" else "",
                    // opens this exact email in Gmail (browser or app), wherever it is, Spam included
                    link = msgId?.let { "https://mail.google.com/mail/u/?authuser=${Uri.encode(account.address)}#search/" +
                        Uri.encode("in:anywhere rfc822msgid:$it") } ?: "")
            }.also { folder.close(false) }
        }
    }

    /** Gmail search syntax for a proof plan. */
    fun query(senders: List<String>, keywords: List<String>, after: String?, before: String?): String {
        val parts = mutableListOf<String>()
        if (senders.isNotEmpty()) parts += senders.joinToString(" OR ", "{", "}") { "from:${it.trim()}" }
        if (keywords.isNotEmpty()) parts += keywords.joinToString(" ", "{", "}") { "\"${it.replace("\"", "")}\"" }
        after?.let { parts += "after:" + it.replace('-', '/') }
        before?.let { parts += "before:" + it.replace('-', '/') }
        return parts.joinToString(" ")
    }
}
