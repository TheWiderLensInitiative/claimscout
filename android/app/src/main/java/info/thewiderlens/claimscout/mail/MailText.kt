package info.thewiderlens.claimscout.mail

import javax.mail.Multipart
import javax.mail.Part

/** Readable text of an email, trimmed: what the PC's AI reads to find order numbers and amounts. */
object MailText {
    const val MAX = 4000

    fun of(p: Part): String = clean(find(p, plain = true) ?: find(p, plain = false)?.let(::stripHtml) ?: "").take(MAX)

    private fun find(p: Part, plain: Boolean): String? = runCatching {
        when {
            p.isMimeType("text/plain") && plain -> p.content as? String
            p.isMimeType("text/html") && !plain -> p.content as? String
            p.isMimeType("multipart/*") -> (p.content as Multipart).let { mp ->
                (0 until mp.count).firstNotNullOfOrNull { find(mp.getBodyPart(it), plain) }
            }
            else -> null
        }
    }.getOrNull()

    fun stripHtml(html: String): String = html
        .replace(Regex("(?is)<(script|style|head)\\b.*?</\\1>"), " ")
        .replace(Regex("(?i)<(br|/p|/div|/tr|/li|/h\\d)[^>]*>"), "\n")
        .replace(Regex("<[^>]+>"), " ")
        .replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        .replace("&#39;", "'").replace("&quot;", "\"")

    fun clean(s: String): String = s.replace(Regex("[ \\t\\u00a0]+"), " ").replace(Regex("\\n\\s*\\n+"), "\n").trim()
}
