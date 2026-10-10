package info.thewiderlens.claimscout.work

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import info.thewiderlens.claimscout.ClaimScoutApp
import info.thewiderlens.claimscout.MainActivity
import info.thewiderlens.claimscout.R
import info.thewiderlens.claimscout.data.Api
import info.thewiderlens.claimscout.data.Payout
import info.thewiderlens.claimscout.mail.PayoutWatch

/** Every few hours: search the inboxes (Spam too) for settlement payments and say so before they expire. */
class PayoutWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    companion object { const val CHANNEL = "payouts" }

    override suspend fun doWork(): Result {
        val store = (applicationContext as ClaimScoutApp).store
        val pairing = store.pairing() ?: return Result.success()
        if (store.accounts().isEmpty()) return Result.success()
        val r = try {
            PayoutWatch(store, Api(pairing) { store.setPairing(pairing.copy(lastGood = it)) }).run()
        } catch (e: Exception) {
            return Result.success()   // PC off or away from home: the next run looks back far enough to catch up
        }
        notify(applicationContext, r.new.filter { it.needs_action })
        return Result.success()
    }
}

fun notify(ctx: Context, payouts: List<Payout>) {
    if (payouts.isEmpty() || ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
    val nm = NotificationManagerCompat.from(ctx)
    payouts.take(6).forEach { p ->
        val open = PendingIntent.getActivity(ctx, ("payout" + p.id).hashCode(),
            Intent(ctx, MainActivity::class.java).putExtra("tab", "claims"),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val title = when (p.kind) {
            "deficiency" -> "Action needed on your claim"
            else -> "Money waiting: ${p.label.lowercase()}" + (p.amount?.let { " $it" } ?: "")
        }
        val text = listOfNotNull(p.settlement, p.expires?.let { "expires $it" },
            if (p.folder == "spam" || p.folder == "junk") "found in your Spam folder" else null).joinToString(" · ")
        nm.notify(("payout" + p.id).hashCode(), NotificationCompat.Builder(ctx, PayoutWorker.CHANNEL)
            .setSmallIcon(R.drawable.ic_notification).setColor(0xFF0081FE.toInt())
            .setContentTitle(title).setContentText(text.ifEmpty { p.subject ?: "" })
            .setStyle(NotificationCompat.BigTextStyle().bigText(listOfNotNull(text, p.action).joinToString("\n")))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(open).setAutoCancel(true).build())
    }
}
